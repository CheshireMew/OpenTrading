from __future__ import annotations

from typing import Any, Literal

from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.price_repository import PriceRepository
from app.infra.persistence.market.history.price_artifacts import PriceArtifactStore
from app.infra.persistence.market.history.indicator_artifacts import IndicatorArtifactStore
from config.market_data import MarketDataConfig


class PriceIndicatorService:
    """Resolve a formal snapshot and delegate its immutable indicator persistence."""

    def __init__(self, database: MarketHistoryDatabase, config: MarketDataConfig) -> None:
        self._prices = PriceRepository(database)
        self.artifacts = PriceArtifactStore(database.root, config)
        self._indicators = IndicatorArtifactStore(self.artifacts, config)

    def materialize(self, canonical_code: str, *, snapshot_hash: str | None = None,
                    basis: Literal["raw", "adjusted"] = "raw") -> dict[str, Any]:
        snapshot = self._prices.load_price_snapshot(canonical_code, snapshot_hash)
        return self._indicators.materialize(snapshot, basis)
