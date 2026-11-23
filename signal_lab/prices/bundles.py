from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from signal_lab.config import SignalLabConfig
from signal_lab.data.snapshots import RawSnapshotStore
from signal_lab.prices.artifacts import PriceArtifactStore
from signal_lab.prices.bundle_contract import BUNDLE_SCHEMA_VERSION
from signal_lab.prices.bundle_inspection import (
    ValidatedBundle,
    ValidatedRawSnapshot as ValidatedRawSnapshot,
    inspect_bundle,
    instrument_record,
)
from signal_lab.prices.bundle_lineage import raw_evidence_hashes, snapshot_closure
from signal_lab.prices.contracts import content_hash, load_json_document
from signal_lab.prices.models import PriceSnapshot
from signal_lab.storage.artifacts import artifact_json
from signal_lab.storage.bundle_import_repository import BundleImportRepository
from signal_lab.storage.capacity import (
    OPERATION_MANIFEST,
    OPERATION_SCHEMA_VERSION,
    ManagedStorage,
    operation_storage_evidence,
)
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.file_integrity import file_sha256
from signal_lab.storage.price_repository import PriceRepository
from signal_lab.storage.raw_snapshots import RawSnapshotRepository


class SnapshotBundleService:
    """Export and atomically register verified offline price snapshot bundles."""

    def __init__(self, root: Path, config: SignalLabConfig) -> None:
        self.root = root.expanduser().resolve()
        self.config = config
        database = SignalLabDatabase(self.root)
        self._prices = PriceRepository(database)
        self._imports = BundleImportRepository(database)
        self._raw_repository = RawSnapshotRepository(database)
        self.artifacts = PriceArtifactStore(self.root, config)

    def export_bundle(
        self,
        destination: Path,
        *,
        snapshot_hashes: list[str] | None = None,
        instruments: list[str] | None = None,
    ) -> dict[str, Any]:
        target = destination.expanduser().resolve()
        snapshots = self._prices.list_price_snapshots(
            snapshot_hashes=snapshot_hashes,
            canonical_codes=instruments,
        )
        if not snapshots:
            raise ValueError("bundle selection contains no price snapshots")
        selected_hashes = [item.snapshot_hash for item in snapshots]
        if snapshot_hashes is not None and set(selected_hashes) != set(snapshot_hashes):
            missing = sorted(set(snapshot_hashes) - set(selected_hashes))
            raise ValueError(f"price snapshots do not exist: {', '.join(missing)}")
        snapshots = snapshot_closure(self._prices, snapshots)
        selected_hashes = [item.snapshot_hash for item in snapshots]
        operation_id = _bundle_operation_id(selected_hashes)
        staging = target.parent / f".{target.name}.staging-{operation_id[-12:]}"
        storage = ManagedStorage(
            self.root,
            maximum_managed_bytes=self.config.max_managed_bytes,
            minimum_free_bytes=self.config.min_free_bytes,
            additional_roots=(target, staging),
        )
        if target.exists():
            existing = inspect_bundle(target)
            if {item.snapshot_hash for item in existing.snapshots} != set(selected_hashes):
                raise FileExistsError(f"bundle destination already exists with different content: {target}")
            if (target / OPERATION_MANIFEST).is_file():
                _write_bundle_operation(
                    target,
                    operation_id=operation_id,
                    status="published",
                    inventory=_bundle_inventory(existing.manifest),
                )
            storage.register_root(
                target,
                producer="snapshot-bundle",
                operation_id=operation_id,
                status="active",
            )
            return _bundle_summary(existing, status="ok")
        estimated_bytes = _estimate_bundle_bytes(self, snapshots)
        preflight = storage.preflight(
            "snapshot-bundle",
            estimated_peak_bytes=estimated_bytes,
        )
        storage.register_root(
            staging,
            producer="snapshot-bundle",
            operation_id=operation_id,
            status="active",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.mkdir(parents=True, exist_ok=True)
        _write_bundle_operation(
            staging,
            operation_id=operation_id,
            status="staging",
            inventory=[],
            preflight=asdict(preflight),
        )
        try:
            validated = self._write_bundle_staging(staging, snapshots)
            inventory = _bundle_inventory(validated.manifest)
            _write_bundle_operation(
                staging,
                operation_id=operation_id,
                status="artifacts_ready",
                inventory=inventory,
            )
            validated = inspect_bundle(staging)
            staging.replace(target)
            _write_bundle_operation(
                target,
                operation_id=operation_id,
                status="published",
                inventory=inventory,
            )
            storage.register_root(
                staging,
                producer="snapshot-bundle",
                operation_id=operation_id,
                status="retired",
            )
            storage.register_root(
                target,
                producer="snapshot-bundle",
                operation_id=operation_id,
                status="active",
            )
            return {
                **_bundle_summary(validated, status="ok"),
                "path": str(target),
            }
        except Exception as exc:
            operation_root = target if (target / OPERATION_MANIFEST).is_file() else staging
            if (operation_root / OPERATION_MANIFEST).is_file():
                try:
                    _write_bundle_operation(
                        operation_root,
                        operation_id=operation_id,
                        status="failed",
                        inventory=[],
                        error=f"{type(exc).__name__}: {exc}",
                    )
                except (OSError, ValueError, RuntimeError):
                    pass
            raise

    def _write_bundle_staging(
        self,
        staging: Path,
        snapshots: list[PriceSnapshot],
    ) -> ValidatedBundle:
        raw_entries: dict[str, dict[str, Any]] = {}
        snapshot_entries: list[dict[str, Any]] = []
        for snapshot in snapshots:
            artifact = self.artifacts.write_snapshot(snapshot)
            artifact_source = Path(artifact["path"])
            artifact_relative = f"snapshots/{snapshot.snapshot_hash}/history.parquet"
            artifact_target = staging / artifact_relative
            artifact_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact_source, artifact_target)
            evidence_hashes: list[str] = []
            for raw_hash in raw_evidence_hashes(snapshot):
                record = self._raw_repository.record(raw_hash)
                if record is None:
                    raise ValueError(
                        "price snapshot cannot be bundled without its raw evidence: "
                        f"{snapshot.snapshot_hash} -> {raw_hash}"
                    )
                evidence_hashes.append(raw_hash)
                requested_acquisitions = set(
                    snapshot.metadata.get("source_acquisition_ids", [])
                )
                acquisitions = self._raw_repository.acquisitions(raw_hash)
                if requested_acquisitions:
                    acquisitions = [
                        item for item in acquisitions
                        if item["acquisition_id"] in requested_acquisitions
                    ]
                if not acquisitions:
                    raise ValueError(
                        f"price snapshot has no registered acquisition for raw evidence: {raw_hash}"
                    )
                acquisition_entries = [
                    {
                        "acquisition_id": item["acquisition_id"],
                        "provider": item["provider"],
                        "resource": item["resource"],
                        "retrieved_at": item["retrieved_at"],
                    }
                    for item in acquisitions
                ]
                if raw_hash in raw_entries:
                    existing_ids = {
                        item["acquisition_id"]
                        for item in raw_entries[raw_hash]["acquisitions"]
                    }
                    raw_entries[raw_hash]["acquisitions"].extend(
                        item for item in acquisition_entries
                        if item["acquisition_id"] not in existing_ids
                    )
                    raw_entries[raw_hash]["acquisitions"].sort(
                        key=lambda item: item["acquisition_id"]
                    )
                    continue
                raw_source = Path(record["path"])
                raw_relative = f"raw/{raw_hash}.json.gz"
                raw_target = staging / raw_relative
                raw_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(raw_source, raw_target)
                raw_entries[raw_hash] = {
                    "snapshot_hash": raw_hash,
                    "acquisitions": acquisition_entries,
                    "path": raw_relative,
                    "size_bytes": raw_target.stat().st_size,
                    "file_sha256": file_sha256(raw_target),
                }
            snapshot_entries.append(
                {
                    "snapshot_hash": snapshot.snapshot_hash,
                    "identity_version": snapshot.identity_version,
                    "instrument": instrument_record(snapshot.instrument),
                    "timeframe": snapshot.timeframe,
                    "provider": snapshot.provider,
                    "provider_symbol": snapshot.provider_symbol,
                    "requested_start": snapshot.requested_start.isoformat(),
                    "requested_end": snapshot.requested_end.isoformat(),
                    "retrieved_at": snapshot.retrieved_at.isoformat(),
                    "source_snapshot_hash": snapshot.source_snapshot_hash,
                    "raw_evidence_hashes": evidence_hashes,
                    "price_basis": snapshot.price_basis,
                    "coverage_status": snapshot.coverage_status,
                    "metadata": snapshot.metadata,
                    "coverage_issues": self._prices.coverage_issues(snapshot.snapshot_hash),
                    "artifact": {
                        "path": artifact_relative,
                        "size_bytes": artifact_target.stat().st_size,
                        "file_sha256": file_sha256(artifact_target),
                        "parquet_schema_version": artifact["parquet_schema_version"],
                        "row_count": len(snapshot.bars),
                    },
                }
            )
        manifest = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "snapshots": snapshot_entries,
            "raw_snapshots": [raw_entries[key] for key in sorted(raw_entries)],
        }
        artifact_json(staging / "manifest.json", manifest)
        return inspect_bundle(staging)

    def inspect_bundle(self, path: Path) -> dict[str, Any]:
        return _bundle_summary(inspect_bundle(path.expanduser().resolve()), status="ok")

    def import_bundle(self, path: Path) -> dict[str, Any]:
        validated = inspect_bundle(path.expanduser().resolve())
        import_id = uuid4().hex
        self._imports.begin_bundle_import(
            import_id=import_id,
            bundle_hash=validated.bundle_hash,
            bundle_path=validated.root,
        )
        try:
            for item in validated.raw_snapshots:
                manifest = item.manifest
                for acquisition in manifest["acquisitions"]:
                    saved = RawSnapshotStore(self.root, self.config).save(
                        acquisition["provider"],
                        acquisition["resource"],
                        item.payload,
                        datetime.fromisoformat(acquisition["retrieved_at"]),
                    )
                    if (
                        saved.snapshot_hash != manifest["snapshot_hash"]
                        or saved.acquisition_id != acquisition["acquisition_id"]
                    ):
                        raise ValueError(
                            f"raw snapshot acquisition changed during import: "
                            f"{acquisition['acquisition_id']}"
                        )
            for snapshot in validated.snapshots:
                self.artifacts.write_snapshot(snapshot)
            self._imports.complete_bundle_import(
                import_id=import_id,
                snapshots=validated.snapshots,
                coverage_by_snapshot={
                    key: tuple(value)
                    for key, value in validated.coverage_by_snapshot.items()
                },
                details={
                    "bundle_hash": validated.bundle_hash,
                    "snapshot_hashes": [item.snapshot_hash for item in validated.snapshots],
                },
            )
        except Exception as exc:
            self._imports.fail_bundle_import(import_id, str(exc))
            raise
        return {
            **_bundle_summary(validated, status="ok"),
            "import_id": import_id,
        }

def _estimate_bundle_bytes(service: SnapshotBundleService, snapshots: list[PriceSnapshot]) -> int:
    total = 1024 * 1024
    raw_hashes: set[str] = set()
    for snapshot in snapshots:
        artifact = service.artifacts.snapshot_directory(snapshot) / "history.parquet"
        total += artifact.stat().st_size if artifact.is_file() else max(
            2 * 1024 * 1024,
            len(snapshot.bars) * 512,
        )
        raw_hashes.update(raw_evidence_hashes(snapshot))
    for raw_hash in raw_hashes:
        record = service._raw_repository.record(raw_hash)
        if record is None:
            raise ValueError(f"bundle raw evidence is missing: {raw_hash}")
        total += Path(record["path"]).stat().st_size
    return total


def _bundle_operation_id(snapshot_hashes: list[str]) -> str:
    return f"bundle-{content_hash({'snapshot_hashes': sorted(snapshot_hashes)})[:24]}"


def _bundle_inventory(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = [
        {
            "class": "deliverable",
            "path": "manifest.json",
        }
    ]
    for item in manifest["snapshots"]:
        artifact = item["artifact"]
        inventory.append(
            {
                "class": "deliverable",
                "path": artifact["path"],
                "size_bytes": artifact["size_bytes"],
                "sha256": artifact["file_sha256"],
                "row_count": artifact["row_count"],
            }
        )
    for item in manifest["raw_snapshots"]:
        inventory.append(
            {
                "class": "evidence",
                "path": item["path"],
                "size_bytes": item["size_bytes"],
                "sha256": item["file_sha256"],
            }
        )
    return inventory


def _write_bundle_operation(
    directory: Path,
    *,
    operation_id: str,
    status: str,
    inventory: list[dict[str, Any]],
    preflight: dict[str, Any] | None = None,
    error: str | None = None,
) -> Path:
    path = directory / OPERATION_MANIFEST
    existing: dict[str, Any] | None = None
    if path.is_file():
        loaded = load_json_document(path)
        if not isinstance(loaded, dict):
            raise ValueError(f"snapshot bundle operation manifest must be an object: {path}")
        existing = loaded
        if (
            existing.get("operation_id") != operation_id
            or existing.get("producer") != "snapshot-bundle"
            or existing.get("owner") != "signal-lab"
        ):
            raise RuntimeError(f"snapshot bundle operation identity collision: {directory}")
    now = datetime.now(timezone.utc).isoformat()
    previous_status = str((existing or {}).get("status", "new"))
    evidence = operation_storage_evidence(
        directory,
        inventory,
        previous_status=previous_status,
        status=status,
        previous_inventory=(existing or {}).get("inventory", []),
    )
    payload = {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_id": operation_id,
        "producer": "snapshot-bundle",
        "owner": "signal-lab",
        "status": status,
        "preflight": preflight or (existing or {}).get("preflight"),
        "inventory": inventory,
        **evidence,
        "cleanup_policy": "report-only",
        "error": error,
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    return artifact_json(path, payload)


def _bundle_summary(validated: ValidatedBundle, *, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_hash": validated.bundle_hash,
        "path": str(validated.root),
        "snapshot_count": len(validated.snapshots),
        "raw_snapshot_count": len(validated.raw_snapshots),
        "snapshot_hashes": [item.snapshot_hash for item in validated.snapshots],
    }
