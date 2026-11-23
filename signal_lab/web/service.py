from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Callable, cast

from signal_lab.config import SignalLabConfig
from signal_lab.storage import SignalLabDatabase

if TYPE_CHECKING:
    from signal_lab.web.liquidity_view import LiquidityView
    from signal_lab.web.price_view import PriceReadView
    from signal_lab.web.workbench_view import WorkbenchView


@dataclass(slots=True)
class WebServices:
    """Compose route-level services over one canonical database boundary."""

    config: SignalLabConfig
    root: Path
    persistence: SignalLabDatabase
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _workbench: Any = field(default=None, init=False, repr=False)
    _liquidity: Any = field(default=None, init=False, repr=False)
    _prices: Any = field(default=None, init=False, repr=False)

    @classmethod
    def create(cls, config: SignalLabConfig, root: Path) -> WebServices:
        resolved_root = root.resolve()
        return cls(config, resolved_root, SignalLabDatabase(resolved_root))

    @property
    def workbench(self) -> WorkbenchView:
        def create() -> WorkbenchView:
            from signal_lab.web.workbench_view import WorkbenchView
            return WorkbenchView(self.persistence)

        return cast("WorkbenchView", self._get("_workbench", create))

    @property
    def liquidity(self) -> LiquidityView:
        def create() -> LiquidityView:
            from signal_lab.web.liquidity_view import LiquidityView
            return LiquidityView(self.config, self.root, self.persistence)

        return cast("LiquidityView", self._get("_liquidity", create))

    @property
    def prices(self) -> PriceReadView:
        def create() -> PriceReadView:
            from signal_lab.web.price_view import PriceReadView
            return PriceReadView(self.config, self.root, self.persistence)

        return cast("PriceReadView", self._get("_prices", create))

    def _get(self, attribute: str, factory: Callable[[], Any]) -> Any:
        with self._lock:
            value = getattr(self, attribute)
            if value is None:
                value = factory()
                setattr(self, attribute, value)
            return value
