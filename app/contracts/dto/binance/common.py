from __future__ import annotations

from pydantic import BaseModel, Field

class BinanceTickerStatsItemResponse(BaseModel):
    symbol: str | None = None
    price_change: float | None = None
    price_change_pct: float | None = Field(default=None, description="24-hour change in percentage points (1.25 means 1.25%)")
    weighted_avg_price: float | None = None
    last_price: float | None = None
    last_qty: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    volume: float | None = None
    quote_volume: float | None = None
    open_time: int | None = None
    close_time: int | None = None
    count: int | None = None


class BinanceTickerStatsResponse(BaseModel):
    exchange: str
    market: str
    items: list[BinanceTickerStatsItemResponse] = Field(default_factory=list)




