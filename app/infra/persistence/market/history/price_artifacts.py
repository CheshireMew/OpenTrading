from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import pandas as pd
import pyarrow.parquet as pq

from config.market_data import MarketDataConfig
from app.domain.market.history.models import PriceSnapshot
from app.infra.persistence.market.history.artifact_publication import ArtifactPublisher
from app.infra.persistence.market.history.file_integrity import file_sha256


PARQUET_SCHEMA_VERSION = "price-bars.v1"


class PriceArtifactStore:
    """Price-specific paths and metadata over the shared artifact publisher."""

    def __init__(self, root: Path, config: MarketDataConfig) -> None:
        self.root = root.expanduser().resolve()
        self.publisher = ArtifactPublisher(self.root, config)

    def write_snapshot(self, snapshot: PriceSnapshot, *, export: Literal["csv", "json"] | None = None) -> dict[str, Any]:
        destination = self.snapshot_directory(snapshot) / "history.parquet"
        exports = self.publisher.table(
            snapshot_frame(snapshot), destination, producer="price-snapshot-artifact",
            operation_id=f"snapshot-{snapshot.snapshot_hash}-{export or 'parquet'}",
            metadata={b"signal_lab_parquet_schema_version": PARQUET_SCHEMA_VERSION.encode("ascii"),
                      b"signal_lab_snapshot_hash": snapshot.snapshot_hash.encode("ascii")},
            estimated_peak_bytes=max(2 * 1024 * 1024, len(snapshot.bars) * 2048), export=export,
        )
        return artifact_payload(destination, len(snapshot.bars), exports, snapshot.snapshot_hash)

    def write_comparison(self, frame: pd.DataFrame, *, export: Literal["csv", "json"] | None = None) -> dict[str, Any]:
        output = frame.copy()
        output.index.name = "date"
        output = output.reset_index()
        content_hash = sha256(output.to_json(orient="records", date_format="iso").encode("utf-8")).hexdigest()
        destination = self.root / "exports" / "prices" / "_comparisons" / "1d" / content_hash / "comparison.parquet"
        exports = self.publisher.table(
            output, destination, producer="price-comparison-artifact", operation_id=f"comparison-{content_hash}-{export or 'parquet'}",
            metadata={b"signal_lab_parquet_schema_version": PARQUET_SCHEMA_VERSION.encode("ascii")},
            estimated_peak_bytes=max(2 * 1024 * 1024, int(output.memory_usage(index=True, deep=True).sum()) * 3), export=export,
        )
        return artifact_payload(destination, len(output), exports)

    def snapshot_directory(self, snapshot: PriceSnapshot) -> Path:
        safe_code = quote(snapshot.instrument.canonical_code, safe=".-@")
        return self.root / "exports" / "prices" / safe_code / snapshot.timeframe / snapshot.snapshot_hash

    @staticmethod
    def read_frame(path: str | Path) -> pd.DataFrame:
        return pd.read_parquet(path)


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
