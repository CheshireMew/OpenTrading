from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.domain.market.history.indicators import (
    INDICATOR_SCHEMA_VERSION,
    indicator_definitions_payload,
    indicator_frame,
    indicator_registry_hash,
)
from app.infra.persistence.market.history.price_artifacts import PriceArtifactStore, frame_semantic_sha256
from app.infra.persistence.market.history.artifacts import storage_item
from app.infra.persistence.market.history.capacity import ManagedStorage
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.file_integrity import file_sha256
from app.infra.persistence.market.history.price_repository import PriceRepository
from config.market_data import MarketDataConfig


class PriceIndicatorService:
    """Materialize deterministic indicator series for one immutable price snapshot."""

    def __init__(self, root: Path, config: MarketDataConfig) -> None:
        self.root = root.expanduser().resolve()
        self.config = config
        self._prices = PriceRepository(MarketHistoryDatabase(self.root))
        self.artifacts = PriceArtifactStore(self.root, config)

    def materialize(
        self,
        canonical_code: str,
        *,
        snapshot_hash: str | None = None,
        basis: Literal["raw", "adjusted"] = "raw",
    ) -> dict[str, Any]:
        snapshot = self._prices.load_price_snapshot(canonical_code, snapshot_hash)
        registry_hash = indicator_registry_hash()
        destination = (
            self.artifacts.snapshot_directory(snapshot)
            / f"indicators-{basis}-{registry_hash[:16]}.parquet"
        )
        expected = {
            b"signal_lab_indicator_schema_version": INDICATOR_SCHEMA_VERSION.encode("ascii"),
            b"signal_lab_snapshot_hash": snapshot.snapshot_hash.encode("ascii"),
            b"signal_lab_indicator_basis": basis.encode("ascii"),
            b"signal_lab_indicator_registry_hash": registry_hash.encode("ascii"),
        }
        if not destination.exists():
            storage = ManagedStorage(
                self.root,
                maximum_managed_bytes=self.config.max_managed_bytes,
                minimum_free_bytes=self.config.min_free_bytes,
            )
            preflight = storage.preflight(
                "price-indicator-artifact",
                estimated_peak_bytes=max(4 * 1024 * 1024, len(snapshot.bars) * 2048),
            )
            operation_id = f"indicator-{snapshot.snapshot_hash}-{basis}-{registry_hash[:16]}"
            operation = storage.operation_directory("price-indicator-artifact", operation_id)
            storage.begin_operation(
                operation,
                operation_id=operation_id,
                producer="price-indicator-artifact",
                preflight=preflight,
            )
            temporary = operation / "indicators.parquet.tmp"
            try:
                frame = indicator_frame(snapshot, basis)
                table = pa.Table.from_pandas(frame, preserve_index=False)
                metadata = dict(table.schema.metadata or {})
                metadata.update(expected)
                metadata[b"signal_lab_semantic_sha256"] = frame_semantic_sha256(frame).encode(
                    "ascii"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(table.replace_schema_metadata(metadata), temporary, compression="zstd")
                temporary.replace(destination)
                storage.finish_operation(
                    operation,
                    status="published",
                    inventory=[storage_item(destination, "cache")],
                )
            except BaseException as exc:
                inventory = [
                    storage_item(path, "temporary")
                    for path in (temporary, destination)
                    if path.is_file()
                ]
                storage.finish_failure(
                    operation,
                    error=exc,
                    inventory=inventory,
                )
                raise
        metadata = pq.read_schema(destination).metadata or {}
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError(f"immutable indicator artifact metadata mismatch: {destination}")
        row_count = pq.read_metadata(destination).num_rows
        if row_count != len(snapshot.bars):
            raise ValueError(f"immutable indicator artifact row count mismatch: {destination}")
        semantic_hash = metadata.get(b"signal_lab_semantic_sha256")
        actual_semantic_hash = frame_semantic_sha256(pd.read_parquet(destination)).encode("ascii")
        if semantic_hash is None or semantic_hash != actual_semantic_hash:
            raise ValueError(f"immutable indicator artifact content mismatch: {destination}")
        return {
            "path": str(destination.resolve()),
            "rows": row_count,
            "sha256": file_sha256(destination),
            "snapshot_hash": snapshot.snapshot_hash,
            "basis": basis,
            "indicator_schema_version": INDICATOR_SCHEMA_VERSION,
            "indicator_registry_hash": registry_hash,
            "definitions": indicator_definitions_payload(),
        }
