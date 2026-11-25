from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Callable, cast

from config.market_data import MarketDataConfig
from app.infra.persistence.market.history import MarketHistoryDatabase

if TYPE_CHECKING:
    from app.services.market.history.liquidity_view import LiquidityView
    from app.services.market.history.price_view import PriceReadView
    from app.services.market.history.workbench_view import WorkbenchView


@dataclass(slots=True)
class MarketDataViews:
    """Compose route-level services over one canonical database boundary."""

    config: MarketDataConfig
    root: Path
    persistence: MarketHistoryDatabase
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _workbench: Any = field(default=None, init=False, repr=False)
    _liquidity: Any = field(default=None, init=False, repr=False)
    _prices: Any = field(default=None, init=False, repr=False)

    @classmethod
    def create(cls, config: MarketDataConfig, database: MarketHistoryDatabase) -> MarketDataViews:
        return cls(config, database.root, database)

    @property
    def workbench(self) -> WorkbenchView:
        def create() -> WorkbenchView:
            from app.services.market.history.workbench_view import WorkbenchView
            return WorkbenchView(self.persistence)

        return cast("WorkbenchView", self._get("_workbench", create))

    @property
    def liquidity(self) -> LiquidityView:
        def create() -> LiquidityView:
            from app.services.market.history.liquidity_view import LiquidityView
            return LiquidityView(self.config, self.root, self.persistence)

        return cast("LiquidityView", self._get("_liquidity", create))

    @property
    def prices(self) -> PriceReadView:
        def create() -> PriceReadView:
            from app.services.market.history.price_view import PriceReadView
            return PriceReadView(self.config, self.root, self.persistence)

        return cast("PriceReadView", self._get("_prices", create))

    def _get(self, attribute: str, factory: Callable[[], Any]) -> Any:
        with self._lock:
            value = getattr(self, attribute)
            if value is None:
                value = factory()
                setattr(self, attribute, value)
            return value
