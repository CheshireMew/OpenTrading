from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from signal_lab.immutability import deep_freeze
from signal_lab.prices.artifacts import PARQUET_SCHEMA_VERSION
from signal_lab.prices.bundle_contract import validate_manifest
from signal_lab.prices.bundle_lineage import (
    lineage_snapshot_hashes,
    raw_evidence_hashes,
)
from signal_lab.prices.contracts import (
    canonical_json_bytes,
    content_hash,
    load_json_document,
)
from signal_lab.prices.models import Instrument, PriceBar, PriceSnapshot
from signal_lab.storage.capacity import OPERATION_MANIFEST
from signal_lab.storage.file_integrity import file_sha256
from signal_lab.structured_data import load_gzip_json_file


@dataclass(frozen=True, slots=True)
class ValidatedRawSnapshot:
    manifest: dict[str, Any]
    payload: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest", deep_freeze(self.manifest))
        object.__setattr__(self, "payload", deep_freeze(self.payload))


@dataclass(frozen=True, slots=True)
class ValidatedBundle:
    root: Path
    manifest: dict[str, Any]
    bundle_hash: str
    snapshots: tuple[PriceSnapshot, ...]
    coverage_by_snapshot: dict[str, list[dict[str, Any]]]
    raw_snapshots: tuple[ValidatedRawSnapshot, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest", deep_freeze(self.manifest))
        object.__setattr__(
            self,
            "coverage_by_snapshot",
            deep_freeze(self.coverage_by_snapshot),
        )

def inspect_bundle(root: Path) -> ValidatedBundle:
    if not root.is_dir():
        raise ValueError(f"snapshot bundle must be a directory: {root}")
    manifest_path = root / "manifest.json"
    manifest = validate_manifest(load_json_document(manifest_path))
    expected_files = {"manifest.json"}
    for item in manifest["snapshots"]:
        expected_files.add(item["artifact"]["path"])
    for item in manifest["raw_snapshots"]:
        expected_files.add(item["path"])
    operation_path = root / OPERATION_MANIFEST
    if operation_path.is_file():
        operation = load_json_document(operation_path)
        if (
            not isinstance(operation, dict)
            or operation.get("owner") != "signal-lab"
            or operation.get("producer") != "snapshot-bundle"
            or operation.get("status") not in {"staging", "artifacts_ready", "published"}
        ):
            raise ValueError(f"snapshot bundle operation manifest is invalid: {operation_path}")
        expected_files.add(OPERATION_MANIFEST)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise ValueError(f"bundle file closure mismatch; missing={missing}, extra={extra}")
    raw_snapshots: list[ValidatedRawSnapshot] = []
    raw_ids: set[str] = set()
    for item in manifest["raw_snapshots"]:
        path = _bundle_child(root, item["path"])
        _verify_file(path, item)
        payload = load_gzip_json_file(path)
        if sha256(canonical_json_bytes(payload)).hexdigest() != item["snapshot_hash"]:
            raise ValueError(f"raw snapshot semantic hash mismatch: {path}")
        raw_ids.add(item["snapshot_hash"])
        raw_snapshots.append(ValidatedRawSnapshot(item, payload))
    snapshots: list[PriceSnapshot] = []
    coverage: dict[str, list[dict[str, Any]]] = {}
    referenced_raw: set[str] = set()
    for item in manifest["snapshots"]:
        artifact = item["artifact"]
        path = _bundle_child(root, artifact["path"])
        _verify_file(path, artifact)
        metadata = pq.read_schema(path).metadata or {}
        if metadata.get(b"signal_lab_snapshot_hash") != item["snapshot_hash"].encode("ascii"):
            raise ValueError(f"price artifact snapshot identity mismatch: {path}")
        if artifact["parquet_schema_version"] != PARQUET_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported price artifact schema: {artifact['parquet_schema_version']}"
            )
        snapshot = snapshot_from_record(item, pd.read_parquet(path))
        if snapshot.snapshot_hash != item["snapshot_hash"]:
            raise ValueError(f"price snapshot semantic hash mismatch: {path}")
        if len(snapshot.bars) != artifact["row_count"]:
            raise ValueError(f"price artifact row count mismatch: {path}")
        evidence = set(item["raw_evidence_hashes"])
        expected_evidence = set(raw_evidence_hashes(snapshot))
        if evidence != expected_evidence:
            raise ValueError(
                f"snapshot raw evidence does not match its provenance: {snapshot.snapshot_hash}"
            )
        if not evidence <= raw_ids:
            raise ValueError(
                f"snapshot references missing raw evidence: {sorted(evidence - raw_ids)}"
            )
        referenced_raw.update(evidence)
        snapshots.append(snapshot)
        coverage[snapshot.snapshot_hash] = item["coverage_issues"]
    if referenced_raw != raw_ids:
        raise ValueError(f"bundle contains unreferenced raw snapshots: {sorted(raw_ids - referenced_raw)}")
    snapshot_ids = {item.snapshot_hash for item in snapshots}
    for snapshot in snapshots:
        missing_lineage = set(lineage_snapshot_hashes(snapshot)) - snapshot_ids
        if missing_lineage:
            raise ValueError(
                f"snapshot lineage is incomplete for {snapshot.snapshot_hash}: "
                f"{sorted(missing_lineage)}"
            )
    return ValidatedBundle(
        root=root,
        manifest=manifest,
        bundle_hash=content_hash(manifest),
        snapshots=tuple(snapshots),
        coverage_by_snapshot=coverage,
        raw_snapshots=tuple(raw_snapshots),
    )

def snapshot_from_record(record: dict[str, Any], frame: pd.DataFrame) -> PriceSnapshot:
    instrument_record = record["instrument"]
    instrument = Instrument(
        canonical_code=instrument_record["canonical_code"],
        name=instrument_record["name"],
        asset_class=instrument_record["asset_class"],
        market=instrument_record["market"],
        exchange=instrument_record["exchange"],
        currency=instrument_record["currency"],
        timezone=instrument_record["timezone"],
        listed_on=date.fromisoformat(instrument_record["listed_on"])
        if instrument_record["listed_on"] else None,
        is_continuous=bool(instrument_record["is_continuous"]),
        metadata=instrument_record["metadata"],
    )
    required_columns = {
        "observed_at", "open", "high", "low", "close", "adjusted_close", "volume",
        "dividend", "split_factor", "instrument", "provider", "source_snapshot_hash",
    }
    if not required_columns <= set(frame.columns):
        raise ValueError(f"price artifact is missing columns: {sorted(required_columns - set(frame.columns))}")
    if set(frame["instrument"].astype(str)) != {instrument.canonical_code}:
        raise ValueError("price artifact instrument does not match manifest")
    if set(frame["provider"].astype(str)) != {record["provider"]}:
        raise ValueError("price artifact provider does not match manifest")
    if set(frame["source_snapshot_hash"].astype(str)) != {record["source_snapshot_hash"]}:
        raise ValueError("price artifact source identity does not match manifest")
    bars = tuple(
        PriceBar(
            observed_at=pd.Timestamp(row["observed_at"]).to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            adjusted_close=float(row["adjusted_close"]),
            volume=float(row["volume"]) if pd.notna(row["volume"]) else None,
            dividend=float(row["dividend"]),
            split_factor=float(row["split_factor"]),
        )
        for _, row in frame.sort_values("observed_at").iterrows()
    )
    return PriceSnapshot(
        instrument=instrument,
        timeframe=record["timeframe"],
        provider=record["provider"],
        provider_symbol=record["provider_symbol"],
        requested_start=date.fromisoformat(record["requested_start"]),
        requested_end=date.fromisoformat(record["requested_end"]),
        retrieved_at=datetime.fromisoformat(record["retrieved_at"]),
        bars=bars,
        source_snapshot_hash=record["source_snapshot_hash"],
        price_basis=record["price_basis"],
        coverage_status=record["coverage_status"],
        metadata=record["metadata"],
        identity_version=record.get("identity_version", 1),
        _persisted_snapshot_hash=(
            record["snapshot_hash"] if record.get("identity_version", 1) == 1 else None
        ),
    )


def instrument_record(instrument: Instrument) -> dict[str, Any]:
    return {
        "canonical_code": instrument.canonical_code,
        "name": instrument.name,
        "asset_class": instrument.asset_class,
        "market": instrument.market,
        "exchange": instrument.exchange,
        "currency": instrument.currency,
        "timezone": instrument.timezone,
        "listed_on": instrument.listed_on.isoformat() if instrument.listed_on else None,
        "is_continuous": instrument.is_continuous,
        "metadata": instrument.metadata,
    }


def _bundle_child(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"invalid bundle path: {relative!r}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"bundle path escapes its root: {relative}") from exc
    return candidate


def _verify_file(path: Path, manifest: dict[str, Any]) -> None:
    if file_sha256(path) != manifest["file_sha256"]:
        raise ValueError(f"file hash mismatch: {path}")
    if path.stat().st_size != manifest["size_bytes"]:
        raise ValueError(f"file size mismatch: {path}")
