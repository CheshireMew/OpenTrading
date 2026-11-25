"""Capacity-checked publication and verification of immutable tabular artifacts."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Literal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.market_data import MarketDataConfig
from app.infra.persistence.market.history.artifacts import storage_item
from app.infra.persistence.market.history.capacity import ManagedStorage, OPERATION_MANIFEST


def serialized_export(frame: pd.DataFrame, format_name: Literal["csv", "json"]) -> bytes:
    if format_name == "csv":
        return frame.to_csv(index=False).encode("utf-8")
    return frame.to_json(orient="records", date_format="iso", force_ascii=False).encode("utf-8")


def verify_parquet(path: Path, frame: pd.DataFrame, metadata: dict[bytes, bytes]) -> None:
    actual = pq.read_metadata(path)
    if any((actual.metadata or {}).get(key) != value for key, value in metadata.items()):
        raise ValueError(f"immutable artifact metadata mismatch: {path}")
    if actual.num_rows != len(frame):
        raise ValueError(f"immutable artifact row count mismatch: {path}")
    try:
        pd.testing.assert_frame_equal(pd.read_parquet(path).reset_index(drop=True),
                                      frame.reset_index(drop=True), check_dtype=False, check_exact=True)
    except AssertionError as exc:
        raise ValueError(f"immutable artifact content mismatch: {path}") from exc


class ArtifactPublisher:
    def __init__(self, root: Path, config: MarketDataConfig) -> None:
        self.storage = ManagedStorage(root, maximum_managed_bytes=config.max_managed_bytes,
                                      minimum_free_bytes=config.min_free_bytes)

    @contextmanager
    def operation(self, producer: str, operation_id: str, estimated_peak_bytes: int, *,
                  inventory: Callable[[], list[dict]], staging: Path | None = None,
                  destination: Path | None = None, failure_inventory: Callable[[], list[dict]] | None = None):
        preflight = self.storage.preflight(producer, estimated_peak_bytes=estimated_peak_bytes)
        operation = staging or self.storage.operation_directory(producer, operation_id)
        self.storage.begin_operation(operation, operation_id=operation_id, producer=producer, preflight=preflight)

        def current():
            return destination if destination is not None and (destination / OPERATION_MANIFEST).is_file() else operation

        try:
            yield operation
            self.storage.finish_operation(current(), status="published", inventory=inventory())
        except BaseException as exc:
            self.storage.try_finish_failure(current(), error=exc, inventory=(failure_inventory or inventory)())
            raise

    def ready(self, directory: Path, inventory: list[dict]) -> None:
        self.storage.finish_operation(directory, status="artifacts_ready", inventory=inventory)

    @staticmethod
    def parquet(frame: pd.DataFrame, destination: Path, metadata: dict[bytes, bytes], operation: Path) -> None:
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = operation / (destination.name + ".tmp")
            table = pa.Table.from_pandas(frame, preserve_index=False)
            table_metadata = dict(table.schema.metadata or {})
            table_metadata.update(metadata)
            pq.write_table(table.replace_schema_metadata(table_metadata), temporary, compression="zstd")
            temporary.replace(destination)
        verify_parquet(destination, frame, metadata)

    @staticmethod
    def export(frame: pd.DataFrame, destination: Path, format_name: Literal["csv", "json"], operation: Path) -> None:
        expected = serialized_export(frame, format_name)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = operation / (destination.name + ".tmp")
            temporary.write_bytes(expected)
            temporary.replace(destination)
        elif destination.read_bytes() != expected:
            raise ValueError(f"immutable export content mismatch: {destination}")

    def table(self, frame: pd.DataFrame, destination: Path, *, producer: str, operation_id: str,
              metadata: dict[bytes, bytes], estimated_peak_bytes: int,
              export: Literal["csv", "json"] | None = None, artifact_class: str = "deliverable") -> list[dict[str, str]]:
        export_path = destination.with_suffix(f".{export}") if export else None
        paths = [path for path in (destination, export_path) if path is not None]
        def inventory():
            return [storage_item(path, artifact_class) for path in paths if path.is_file()]
        if any(not path.exists() for path in paths):
            operation_path = self.storage.operation_directory(producer, operation_id)
            def failed():
                return inventory() + [storage_item(path, "temporary") for path in operation_path.glob("*.tmp") if path.is_file()]
            with self.operation(producer, operation_id, estimated_peak_bytes,
                                inventory=inventory, failure_inventory=failed) as operation:
                self.parquet(frame, destination, metadata, operation)
                if export_path is not None:
                    self.export(frame, export_path, export, operation)
        else:
            verify_parquet(destination, frame, metadata)
            if export_path is not None and export_path.read_bytes() != serialized_export(frame, export):
                raise ValueError(f"immutable export content mismatch: {export_path}")
        return [{"format": export, "path": str(export_path.resolve())}] if export_path is not None else []
