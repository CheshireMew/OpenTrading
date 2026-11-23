from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from signal_lab.config import SignalLabConfig
from signal_lab.prices.models import PriceSnapshot
from signal_lab.storage.artifacts import storage_item, storage_items
from signal_lab.storage.capacity import ManagedStorage
from signal_lab.storage.file_integrity import file_sha256


PARQUET_SCHEMA_VERSION = "price-bars.v1"


class PriceArtifactStore:
    """Unique writer for immutable price and comparison artifacts."""

    def __init__(self, root: Path, config: SignalLabConfig) -> None:
        self.root = root.expanduser().resolve()
        self.config = config

    def write_snapshot(
        self,
        snapshot: PriceSnapshot,
        *,
        export: Literal["csv", "json"] | None = None,
    ) -> dict[str, Any]:
        directory = self.snapshot_directory(snapshot)
        destination = directory / "history.parquet"
        if not destination.exists():
            storage, operation = self._begin_operation(
                "price-snapshot-artifact",
                f"snapshot-{snapshot.snapshot_hash}",
                max(2 * 1024 * 1024, len(snapshot.bars) * 512),
            )
            temporary = operation / "history.parquet.tmp"
            try:
                directory.mkdir(parents=True, exist_ok=True)
                frame = snapshot_frame(snapshot)
                table = pa.Table.from_pandas(frame, preserve_index=False)
                metadata = dict(table.schema.metadata or {})
                metadata[b"signal_lab_parquet_schema_version"] = PARQUET_SCHEMA_VERSION.encode("utf-8")
                metadata[b"signal_lab_snapshot_hash"] = snapshot.snapshot_hash.encode("ascii")
                pq.write_table(table.replace_schema_metadata(metadata), temporary, compression="zstd")
                temporary.replace(destination)
                storage.finish_operation(
                    operation,
                    status="published",
                    inventory=[storage_item(destination, "deliverable")],
                )
            except BaseException as exc:
                storage.finish_failure(
                    operation,
                    error=exc,
                    inventory=storage_items((temporary, destination), "temporary"),
                )
                raise
        metadata = pq.read_schema(destination).metadata or {}
        if metadata.get(b"signal_lab_snapshot_hash") != snapshot.snapshot_hash.encode("ascii"):
            raise ValueError(f"immutable price artifact metadata mismatch: {destination}")
        row_count = pq.read_metadata(destination).num_rows
        if row_count != len(snapshot.bars):
            raise ValueError(f"immutable price artifact row count mismatch: {destination}")
        try:
            pd.testing.assert_frame_equal(
                pd.read_parquet(destination).reset_index(drop=True),
                snapshot_frame(snapshot).reset_index(drop=True),
                check_dtype=False,
                check_exact=True,
            )
        except AssertionError as exc:
            raise ValueError(
                f"immutable price artifact content mismatch: {destination}"
            ) from exc
        exports: list[dict[str, str]] = []
        if export:
            frame = snapshot_frame(snapshot)
            export_path = directory / f"history.{export}"
            expected = _serialized_export(frame, export)
            if not export_path.exists():
                storage, operation = self._begin_operation(
                    "price-snapshot-export",
                    f"snapshot-{snapshot.snapshot_hash}-{export}",
                    len(expected) + 4096,
                )
                temporary = operation / f"history.{export}.tmp"
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    temporary.write_bytes(expected)
                    temporary.replace(export_path)
                    storage.finish_operation(
                        operation,
                        status="published",
                        inventory=[storage_item(export_path, "deliverable")],
                    )
                except BaseException as exc:
                    storage.finish_failure(
                        operation,
                        error=exc,
                        inventory=storage_items((temporary, export_path), "temporary"),
                    )
                    raise
            elif export_path.read_bytes() != expected:
                raise ValueError(f"immutable price export content mismatch: {export_path}")
            exports.append({"format": export, "path": str(export_path.resolve())})
        return artifact_payload(destination, row_count, exports, snapshot.snapshot_hash)

    def write_comparison(
        self,
        frame: pd.DataFrame,
        *,
        export: Literal["csv", "json"] | None = None,
    ) -> dict[str, Any]:
        output = frame.copy()
        output.index.name = "date"
        output = output.reset_index()
        content_hash = sha256(
            output.to_json(orient="records", date_format="iso").encode("utf-8")
        ).hexdigest()
        directory = self.root / "exports" / "prices" / "_comparisons" / "1d" / content_hash
        destination = directory / "comparison.parquet"
        if not destination.exists():
            memory_bytes = int(output.memory_usage(index=True, deep=True).sum())
            storage, operation = self._begin_operation(
                "price-comparison-artifact",
                f"comparison-{content_hash}",
                max(2 * 1024 * 1024, memory_bytes * 2),
            )
            temporary = operation / "comparison.parquet.tmp"
            try:
                directory.mkdir(parents=True, exist_ok=True)
                table = pa.Table.from_pandas(output, preserve_index=False)
                metadata = dict(table.schema.metadata or {})
                metadata[b"signal_lab_parquet_schema_version"] = PARQUET_SCHEMA_VERSION.encode("utf-8")
                pq.write_table(table.replace_schema_metadata(metadata), temporary, compression="zstd")
                temporary.replace(destination)
                storage.finish_operation(
                    operation,
                    status="published",
                    inventory=[storage_item(destination, "deliverable")],
                )
            except BaseException as exc:
                storage.finish_failure(
                    operation,
                    error=exc,
                    inventory=storage_items((temporary, destination), "temporary"),
                )
                raise
        try:
            pd.testing.assert_frame_equal(
                pd.read_parquet(destination).reset_index(drop=True),
                output.reset_index(drop=True),
                check_dtype=False,
                check_exact=True,
            )
        except AssertionError as exc:
            raise ValueError(f"immutable comparison artifact content mismatch: {destination}") from exc
        exports: list[dict[str, str]] = []
        if export:
            export_path = directory / f"comparison.{export}"
            expected = _serialized_export(output, export)
            if not export_path.exists():
                storage, operation = self._begin_operation(
                    "price-comparison-export",
                    f"comparison-{content_hash}-{export}",
                    len(expected) + 4096,
                )
                temporary = operation / f"comparison.{export}.tmp"
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    temporary.write_bytes(expected)
                    temporary.replace(export_path)
                    storage.finish_operation(
                        operation,
                        status="published",
                        inventory=[storage_item(export_path, "deliverable")],
                    )
                except BaseException as exc:
                    storage.finish_failure(
                        operation,
                        error=exc,
                        inventory=storage_items((temporary, export_path), "temporary"),
                    )
                    raise
            elif export_path.read_bytes() != expected:
                raise ValueError(f"immutable comparison export content mismatch: {export_path}")
            exports.append({"format": export, "path": str(export_path.resolve())})
        return artifact_payload(destination, len(output), exports)

    def snapshot_directory(self, snapshot: PriceSnapshot) -> Path:
        safe_code = quote(snapshot.instrument.canonical_code, safe=".-@")
        return self.root / "exports" / "prices" / safe_code / snapshot.timeframe / snapshot.snapshot_hash

    def _begin_operation(
        self,
        producer: str,
        operation_id: str,
        estimated_peak_bytes: int,
    ) -> tuple[ManagedStorage, Path]:
        storage = ManagedStorage(
            self.root,
            maximum_managed_bytes=self.config.max_managed_bytes,
            minimum_free_bytes=self.config.min_free_bytes,
        )
        preflight = storage.preflight(producer, estimated_peak_bytes=estimated_peak_bytes)
        operation = storage.operation_directory(producer, operation_id)
        storage.begin_operation(
            operation,
            operation_id=operation_id,
            producer=producer,
            preflight=preflight,
        )
        return storage, operation

def snapshot_frame(snapshot: PriceSnapshot) -> pd.DataFrame:
    columns = [
        "date", "observed_at", "open", "high", "low", "close", "adjusted_close",
        "volume", "dividend", "split_factor", "instrument", "provider",
        "source_snapshot_hash",
    ]
    return pd.DataFrame(
        [
            {
                "date": bar.observation_date,
                "observed_at": bar.observed_at,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "adjusted_close": bar.adjusted_close,
                "volume": bar.volume,
                "dividend": bar.dividend,
                "split_factor": bar.split_factor,
                "instrument": snapshot.instrument.canonical_code,
                "provider": snapshot.provider,
                "source_snapshot_hash": snapshot.source_snapshot_hash,
            }
            for bar in snapshot.bars
        ],
        columns=columns,
    )


def artifact_payload(
    path: Path,
    rows: int,
    exports: list[dict[str, str]],
    snapshot_hash: str | None = None,
) -> dict[str, Any]:
    digest = file_sha256(path)
    schema = pq.read_schema(path)
    version = (schema.metadata or {}).get(
        b"signal_lab_parquet_schema_version", b"",
    ).decode("utf-8")
    payload: dict[str, Any] = {
        "path": str(path.resolve()),
        "rows": rows,
        "sha256": digest,
        "parquet_schema_version": version,
        "exports": exports,
    }
    if snapshot_hash:
        payload["snapshot_hash"] = snapshot_hash
    return payload


def frame_semantic_sha256(frame: pd.DataFrame) -> str:
    """Hash table values and column order independently from Parquet encoding."""

    document = frame.to_json(
        orient="table",
        date_format="iso",
        date_unit="ns",
        double_precision=15,
        force_ascii=False,
        index=False,
    )
    return sha256(document.encode("utf-8")).hexdigest()


def _serialized_export(frame: pd.DataFrame, format_name: Literal["csv", "json"]) -> bytes:
    if format_name == "csv":
        return frame.to_csv(index=False).encode("utf-8")
    return frame.to_json(
        orient="records", date_format="iso", force_ascii=False,
    ).encode("utf-8")
