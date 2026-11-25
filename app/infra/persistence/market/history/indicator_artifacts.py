from __future__ import annotations

from typing import Any, Literal

from config.market_data import MarketDataConfig
from app.domain.market.history.indicators import (
    INDICATOR_SCHEMA_VERSION, indicator_definitions_payload, indicator_frame, indicator_registry_hash,
)
from app.domain.market.history.models import PriceSnapshot
from app.infra.persistence.market.history.artifact_publication import ArtifactPublisher
from app.infra.persistence.market.history.price_artifacts import PriceArtifactStore, frame_semantic_sha256
from app.infra.persistence.market.history.file_integrity import file_sha256


class IndicatorArtifactStore:
    def __init__(self, artifacts: PriceArtifactStore, config: MarketDataConfig) -> None:
        self.artifacts = artifacts
        self.publisher = ArtifactPublisher(artifacts.root, config)

    def materialize(self, snapshot: PriceSnapshot, basis: Literal["raw", "adjusted"]) -> dict[str, Any]:
        registry_hash = indicator_registry_hash()
        destination = self.artifacts.snapshot_directory(snapshot) / f"indicators-{basis}-{registry_hash[:16]}.parquet"
        frame = indicator_frame(snapshot, basis)
        self.publisher.table(
            frame, destination, producer="price-indicator-artifact",
            operation_id=f"indicator-{snapshot.snapshot_hash}-{basis}-{registry_hash[:16]}",
            estimated_peak_bytes=max(4 * 1024 * 1024, len(snapshot.bars) * 2048), artifact_class="cache",
            metadata={b"signal_lab_indicator_schema_version": INDICATOR_SCHEMA_VERSION.encode("ascii"),
                      b"signal_lab_snapshot_hash": snapshot.snapshot_hash.encode("ascii"),
                      b"signal_lab_indicator_basis": basis.encode("ascii"),
                      b"signal_lab_indicator_registry_hash": registry_hash.encode("ascii"),
                      b"signal_lab_semantic_sha256": frame_semantic_sha256(frame).encode("ascii")},
        )
        return {"path": str(destination.resolve()), "rows": len(frame), "sha256": file_sha256(destination),
                "snapshot_hash": snapshot.snapshot_hash, "basis": basis,
                "indicator_schema_version": INDICATOR_SCHEMA_VERSION, "indicator_registry_hash": registry_hash,
                "definitions": indicator_definitions_payload()}
