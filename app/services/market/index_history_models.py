from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OhlcvRecord:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_row(self) -> list[float]:
        return [self.timestamp, self.open, self.high, self.low, self.close, self.volume]


@dataclass(frozen=True, slots=True)
class MarketIndexHistoryRecord:
    symbol: str
    name: str
    market: str
    currency: str
    native_currency: str
    timeframe: str
    source: str
    price_basis: str
    pricing_symbol: str | None
    pricing_name: str | None
    pricing_currency: str
    is_close_only: bool
    data: list[OhlcvRecord]

    @property
    def count(self) -> int:
        return len(self.data)
