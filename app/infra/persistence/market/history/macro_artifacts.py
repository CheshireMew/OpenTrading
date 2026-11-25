from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import pandas as pd

from config.market_data import MarketDataConfig
from app.infra.persistence.market.history.artifact_publication import ArtifactPublisher
from app.infra.persistence.market.history.price_artifacts import artifact_payload


MACRO_PARQUET_SCHEMA_VERSION = "macro-values.v2"


class MacroArtifactStore:
    def __init__(self, root: Path, config: MarketDataConfig) -> None:
        self.root = root
        self.publisher = ArtifactPublisher(root, config)

    def write(self, series_id: str, snapshot_hash: str, values: list[dict[str, Any]],
              export: Literal["csv", "json"] | None) -> dict[str, Any]:
        directory = self.root / "exports" / "macro" / quote(f"FRED:{series_id}", safe=".-@") / "1d" / snapshot_hash
        exports = self.publisher.table(
            pd.DataFrame(values), directory / "history.parquet", producer="macro-price-artifact",
            operation_id=f"macro-{snapshot_hash}-{export or 'parquet'}",
            metadata={b"signal_lab_parquet_schema_version": MACRO_PARQUET_SCHEMA_VERSION.encode("ascii"),
                      b"signal_lab_snapshot_hash": snapshot_hash.encode("ascii")},
            estimated_peak_bytes=max(4 * 1024 * 1024, len(values) * 2048 + 8192), export=export,
        )
        return artifact_payload(directory / "history.parquet", len(values), exports)
