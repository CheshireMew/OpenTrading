from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.market_data import MarketDataConfig
from app.infra.persistence.market.history.price_artifacts import snapshot_frame
from app.services.market.history.classifications import ClassificationService
from app.infra.persistence.market.history.contracts import content_hash, load_json_document, require_object
from app.domain.market.history.indicators import indicator_frame, indicator_registry_hash
from app.services.market.history.indicators import PriceIndicatorService
from app.services.market.history.prices import PriceService
from app.infra.persistence.market.history.artifacts import artifact_json
from app.infra.persistence.market.history.capacity import ManagedStorage, OPERATION_MANIFEST
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.file_integrity import file_sha256
from app.infra.persistence.market.history.price_repository import PriceRepository
from app.infra.persistence.market.history.price_dataset_repository import PriceDatasetRepository


DATASET_SCHEMA_VERSION = "signal-lab.price-dataset.v1"


class PriceDatasetService:
    """Build immutable partitioned datasets from formal price snapshots."""

    def __init__(self, root: Path, config: MarketDataConfig) -> None:
        self.root = root.expanduser().resolve()
        self.config = config
        database = MarketHistoryDatabase(self.root)
        self._datasets = PriceDatasetRepository(database)
        self.prices = PriceService(self.root, config)
        self.indicators = PriceIndicatorService(self.root, config)
        self.classifications = ClassificationService(self.root, config)

    def build(
        self,
        name: str,
        instruments: list[str],
        *,
        start: date,
        end: date,
        basis: Literal["raw", "adjusted"] = "adjusted",
        refresh: bool = False,
        cache_only: bool = False,
        provider: str | None = None,
        include_indicators: bool = True,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("dataset name is required")
        canonical_inputs = list(dict.fromkeys(instruments))
        if not canonical_inputs:
            raise ValueError("dataset requires at least one instrument")
        histories = [
            self.prices.history(
                instrument,
                start=start,
                end=end,
                basis=basis,
                refresh=refresh,
                cache_only=cache_only,
                provider=provider,
            )
            for instrument in canonical_inputs
        ]
        failed = [item for item in histories if item["status"] not in {"ok", "partial"}]
        if failed:
            reasons = [warning for item in failed for warning in item.get("warnings", [])]
            raise ValueError("dataset member failed: " + "; ".join(reasons))
        status = "ok" if all(item["status"] == "ok" for item in histories) else "partial"
        warnings = list(dict.fromkeys(
            warning for item in histories for warning in item.get("warnings", [])
        ))
        classifications = {
            item["instrument"]["canonical_code"]: self.classifications.memberships(
                item["instrument"]["canonical_code"], as_of=end,
            )
            for item in histories
        }
        registry_hash = indicator_registry_hash() if include_indicators else None
        component_identity = [
            {
                "canonical_code": item["instrument"]["canonical_code"],
                "snapshot_hash": item["artifact"]["snapshot_hash"],
                "coverage": item["coverage"],
                "classifications_as_of_end": classifications[
                    item["instrument"]["canonical_code"]
                ],
            }
            for item in histories
        ]
        dataset_hash = content_hash(
            {
                "schema_version": DATASET_SCHEMA_VERSION,
                "name": name,
                "timeframe": "1d",
                "basis": basis,
                "requested_start": start.isoformat(),
                "requested_end": end.isoformat(),
                "include_indicators": include_indicators,
                "indicator_registry_hash": registry_hash,
                "status": status,
                "warnings": warnings,
                "members": component_identity,
            }
        )
        directory = self.root / "exports" / "datasets" / "prices" / dataset_hash
        manifest_path = directory / "dataset-manifest.json"
        if manifest_path.exists():
            manifest = _inspect_dataset(directory, dataset_hash, self.root)
            self._datasets.save_price_dataset(
                _dataset_database_payload(manifest, manifest_path), manifest["members"],
            )
            if (directory / OPERATION_MANIFEST).is_file():
                ManagedStorage(
                    self.root,
                    maximum_managed_bytes=self.config.max_managed_bytes,
                    minimum_free_bytes=self.config.min_free_bytes,
                ).finish_operation(
                    directory,
                    status="published",
                    inventory=_dataset_inventory(directory, manifest),
                )
            return {
                "status": manifest["status"],
                "dataset_hash": dataset_hash,
                "name": manifest["name"],
                "path": str((directory / "data").resolve()),
                "manifest_path": str(manifest_path.resolve()),
                "row_count": manifest["row_count"],
                "instrument_count": manifest["instrument_count"],
                "warnings": manifest["warnings"],
            }
        if directory.exists():
            raise FileExistsError(f"dataset directory exists without a valid manifest: {directory}")
        storage = ManagedStorage(
            self.root,
            maximum_managed_bytes=self.config.max_managed_bytes,
            minimum_free_bytes=self.config.min_free_bytes,
        )
        source_bytes = sum(Path(item["artifact"]["path"]).stat().st_size for item in histories)
        preflight = storage.preflight(
            "price-dataset",
            estimated_peak_bytes=max(8 * 1024 * 1024, source_bytes * 3),
        )
        staging = directory.parent / ".staging" / dataset_hash
        storage.begin_operation(
            staging,
            operation_id=dataset_hash,
            producer="price-dataset",
            preflight=preflight,
        )
        try:
            manifest, members, total_rows = self._write_staging_dataset(
                staging,
                dataset_hash=dataset_hash,
                name=name,
                start=start,
                end=end,
                basis=basis,
                include_indicators=include_indicators,
                registry_hash=registry_hash,
                status=status,
                warnings=warnings,
                histories=histories,
                classifications=classifications,
            )
            inventory = _dataset_inventory(staging, manifest)
            storage.finish_operation(
                staging,
                status="artifacts_ready",
                inventory=inventory,
            )
            _inspect_dataset(staging, dataset_hash, self.root)
            directory.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(directory)
            payload = _dataset_database_payload(manifest, manifest_path)
            self._datasets.save_price_dataset(payload, members)
            storage.finish_operation(
                directory,
                status="published",
                inventory=inventory,
            )
        except Exception as exc:
            operation_root = directory if (directory / OPERATION_MANIFEST).is_file() else staging
            if (operation_root / OPERATION_MANIFEST).is_file():
                storage.try_finish_failure(operation_root, error=exc, inventory=[])
            raise
        return {
            "status": status,
            "dataset_hash": dataset_hash,
            "name": name,
            "path": str((directory / "data").resolve()),
            "manifest_path": str(manifest_path.resolve()),
            "row_count": total_rows,
            "instrument_count": len(members),
            "warnings": warnings,
        }

    def _write_staging_dataset(
        self,
        staging: Path,
        *,
        dataset_hash: str,
        name: str,
        start: date,
        end: date,
        basis: Literal["raw", "adjusted"],
        include_indicators: bool,
        registry_hash: str | None,
        status: str,
        warnings: list[str],
        histories: list[dict[str, Any]],
        classifications: dict[str, list[dict[str, Any]]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        members: list[dict[str, Any]] = []
        total_rows = 0
        for history in histories:
            code = history["instrument"]["canonical_code"]
            snapshot_hash = history["artifact"]["snapshot_hash"]
            price_frame = pd.read_parquet(history["artifact"]["path"])
            price_frame["basis_price"] = (
                price_frame["adjusted_close"] if basis == "adjusted" else price_frame["close"]
            )
            indicator_artifact: dict[str, Any] | None = None
            if include_indicators:
                indicator_artifact = self.indicators.materialize(
                    code, snapshot_hash=snapshot_hash, basis=basis,
                )
                indicator_frame = pd.read_parquet(indicator_artifact["path"]).drop(
                    columns=["date", "basis", "price", "snapshot_hash"], errors="ignore",
                )
                price_frame = price_frame.merge(indicator_frame, on="observed_at", how="left")
            price_frame["snapshot_hash"] = snapshot_hash
            partition_key = sha256(code.encode("utf-8")).hexdigest()[:16]
            partition_relative = f"data/instrument_key={partition_key}/part-0.parquet"
            partition_path = staging / partition_relative
            partition_path.parent.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pandas(price_frame, preserve_index=False)
            metadata = dict(table.schema.metadata or {})
            metadata.update(
                {
                    b"signal_lab_dataset_schema_version": DATASET_SCHEMA_VERSION.encode("ascii"),
                    b"signal_lab_dataset_hash": dataset_hash.encode("ascii"),
                    b"signal_lab_snapshot_hash": snapshot_hash.encode("ascii"),
                }
            )
            pq.write_table(table.replace_schema_metadata(metadata), partition_path, compression="zstd")
            member = {
                "canonical_code": code,
                "snapshot_hash": snapshot_hash,
                "row_count": len(price_frame),
                "partition_relative_path": partition_relative,
                "partition_sha256": file_sha256(partition_path),
                "coverage": history["coverage"],
                "indicator_artifact": _indicator_reference(indicator_artifact),
                "classifications_as_of_end": classifications[code],
            }
            members.append(member)
            total_rows += len(price_frame)
        created_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema_version": DATASET_SCHEMA_VERSION,
            "dataset_hash": dataset_hash,
            "name": name,
            "timeframe": "1d",
            "basis": basis,
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "created_at": created_at,
            "status": status,
            "warnings": warnings,
            "row_count": total_rows,
            "instrument_count": len(members),
            "include_indicators": include_indicators,
            "indicator_registry_hash": registry_hash,
            "members": members,
        }
        artifact_json(staging / "dataset-manifest.json", manifest)
        return manifest, members, total_rows


def _indicator_reference(artifact: dict[str, Any] | None) -> dict[str, Any] | None:
    if artifact is None:
        return None
    return {
        key: artifact[key]
        for key in (
            "rows", "sha256", "snapshot_hash", "basis", "indicator_schema_version",
            "indicator_registry_hash", "definitions",
        )
    }


def _dataset_database_payload(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    return {
        "dataset_hash": manifest["dataset_hash"],
        "name": manifest["name"],
        "timeframe": manifest["timeframe"],
        "basis": manifest["basis"],
        "requested_start": manifest["requested_start"],
        "requested_end": manifest["requested_end"],
        "created_at": manifest["created_at"],
        "manifest_path": str(manifest_path.resolve()),
        "row_count": manifest["row_count"],
        "instrument_count": manifest["instrument_count"],
        "metadata": {
            "schema_version": DATASET_SCHEMA_VERSION,
            "include_indicators": manifest["include_indicators"],
            "indicator_registry_hash": manifest["indicator_registry_hash"],
            "status": manifest["status"],
            "warnings": manifest["warnings"],
        },
    }


def _dataset_inventory(directory: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = [
        {
            "class": "deliverable",
            "path": "dataset-manifest.json",
            "size_bytes": (directory / "dataset-manifest.json").stat().st_size,
            "sha256": file_sha256(directory / "dataset-manifest.json"),
        }
    ]
    for member in manifest["members"]:
        path = directory / member["partition_relative_path"]
        inventory.append(
            {
                "class": "deliverable",
                "path": member["partition_relative_path"],
                "size_bytes": path.stat().st_size,
                "sha256": member["partition_sha256"],
                "row_count": member["row_count"],
            }
        )
    return inventory


def _inspect_dataset(
    directory: Path,
    expected_hash: str,
    data_root: Path,
) -> dict[str, Any]:
    manifest = require_object(
        load_json_document(directory / "dataset-manifest.json"),
        source="price dataset manifest",
        required={
            "schema_version", "dataset_hash", "name", "timeframe", "basis",
            "requested_start", "requested_end", "created_at", "row_count",
            "instrument_count", "include_indicators", "indicator_registry_hash", "status",
            "warnings", "members",
        },
    )
    if manifest["schema_version"] != DATASET_SCHEMA_VERSION:
        raise ValueError(f"unsupported price dataset schema: {manifest['schema_version']}")
    if manifest["dataset_hash"] != expected_hash:
        raise ValueError("price dataset identity does not match its directory")
    if not isinstance(manifest["members"], list) or not manifest["members"]:
        raise ValueError("price dataset requires at least one member")
    expected_files = {"dataset-manifest.json"}
    row_count = 0
    canonical_codes: set[str] = set()
    prices = PriceRepository(MarketHistoryDatabase(data_root))
    for index, raw in enumerate(manifest["members"]):
        member = require_object(
            raw,
            source=f"price dataset member {index}",
            required={
                "canonical_code", "snapshot_hash", "row_count", "partition_relative_path",
                "partition_sha256", "coverage", "indicator_artifact",
                "classifications_as_of_end",
            },
        )
        if member["canonical_code"] in canonical_codes:
            raise ValueError(f"duplicate price dataset member: {member['canonical_code']}")
        canonical_codes.add(member["canonical_code"])
        relative = member["partition_relative_path"]
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ValueError(f"invalid price dataset partition path: {relative!r}")
        path = (directory / relative).resolve()
        try:
            path.relative_to(directory.resolve())
        except ValueError as exc:
            raise ValueError(f"price dataset partition escapes its root: {relative}") from exc
        if not path.is_file():
            raise ValueError(f"price dataset partition is missing: {relative}")
        if file_sha256(path) != member["partition_sha256"]:
            raise ValueError(f"price dataset partition hash mismatch: {relative}")
        parquet = pq.read_metadata(path)
        metadata = parquet.metadata or {}
        expected_metadata = {
            b"signal_lab_dataset_schema_version": DATASET_SCHEMA_VERSION.encode("ascii"),
            b"signal_lab_dataset_hash": expected_hash.encode("ascii"),
            b"signal_lab_snapshot_hash": member["snapshot_hash"].encode("ascii"),
        }
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise ValueError(f"price dataset partition metadata mismatch: {relative}")
        if parquet.num_rows != member["row_count"]:
            raise ValueError(f"price dataset partition row count mismatch: {relative}")
        snapshot = prices.load_price_snapshot(
            member["canonical_code"], member["snapshot_hash"],
        )
        expected_frame = snapshot_frame(snapshot)
        expected_frame["basis_price"] = (
            expected_frame["adjusted_close"]
            if manifest["basis"] == "adjusted"
            else expected_frame["close"]
        )
        if manifest["include_indicators"]:
            expected_indicators = indicator_frame(snapshot, manifest["basis"]).drop(
                columns=["date", "basis", "price", "snapshot_hash"], errors="ignore",
            )
            expected_frame = expected_frame.merge(
                expected_indicators, on="observed_at", how="left",
            )
        expected_frame["snapshot_hash"] = member["snapshot_hash"]
        try:
            pd.testing.assert_frame_equal(
                pd.read_parquet(path).reset_index(drop=True),
                expected_frame.reset_index(drop=True),
                check_dtype=False,
                check_exact=True,
            )
        except AssertionError as exc:
            raise ValueError(
                f"price dataset partition content does not match its formal snapshot: {relative}"
            ) from exc
        expected_files.add(relative)
        row_count += member["row_count"]
    operation_path = directory / OPERATION_MANIFEST
    if operation_path.is_file():
        operation = load_json_document(operation_path)
        if (
            not isinstance(operation, dict)
            or operation.get("operation_id") != expected_hash
            or operation.get("producer") != "price-dataset"
            or operation.get("status") not in {"artifacts_ready", "published"}
        ):
            raise ValueError("price dataset storage operation manifest is invalid")
        expected_files.add(OPERATION_MANIFEST)
    actual_files = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("price dataset file closure does not match its manifest")
    if manifest["instrument_count"] != len(canonical_codes) or manifest["row_count"] != row_count:
        raise ValueError("price dataset aggregate counts do not match its members")
    semantic_identity = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "name": manifest["name"],
        "timeframe": manifest["timeframe"],
        "basis": manifest["basis"],
        "requested_start": manifest["requested_start"],
        "requested_end": manifest["requested_end"],
        "include_indicators": manifest["include_indicators"],
        "indicator_registry_hash": manifest["indicator_registry_hash"],
        "status": manifest["status"],
        "warnings": manifest["warnings"],
        "members": [
            {
                "canonical_code": member["canonical_code"],
                "snapshot_hash": member["snapshot_hash"],
                "coverage": member["coverage"],
                "classifications_as_of_end": member["classifications_as_of_end"],
            }
            for member in manifest["members"]
        ],
    }
    if content_hash(semantic_identity) != expected_hash:
        raise ValueError("price dataset semantic identity does not match its directory")
    return manifest
