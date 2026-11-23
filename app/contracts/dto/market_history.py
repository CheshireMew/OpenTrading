from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal

from app.contracts.json_types import JsonValue


class BitcoinHalvingResponse(BaseModel):
    block_height: int
    block_timestamp: int
    next_halving_height: int
    estimated_at: int
    confirmed_halvings_after_2024: list[int]


class MACDResponse(BaseModel):
    dif: float | None
    dea: float | None
    histogram: float | None


class IndicatorSummaryResponse(BaseModel):
    ema: float | None
    rsi: float | None
    macd: MACDResponse | None
    atr: float | None
    atr_pct: float | None = None
    realized_volatility_pct: float | None = None
    annualized_volatility_pct: float | None = None


class OhlcvPointResponse(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketHistoryMissingRangeResponse(BaseModel):
    start_ts: int
    end_ts: int


class MarketHistoryCoverageResponse(BaseModel):
    complete: bool
    missing_ranges: list[MarketHistoryMissingRangeResponse] = Field(default_factory=list)


def build_market_history_coverage(
    missing_ranges: list[tuple[int, int]] | None = None,
) -> MarketHistoryCoverageResponse:
    return MarketHistoryCoverageResponse(
        complete=not missing_ranges,
        missing_ranges=[
            MarketHistoryMissingRangeResponse(start_ts=int(start), end_ts=int(end))
            for start, end in (missing_ranges or [])
        ],
    )


class MarketHistoryResponse(BaseModel):
    symbol: str
    timeframe: str
    items: list[OhlcvPointResponse] = Field(default_factory=list)
    coverage: MarketHistoryCoverageResponse = Field(default_factory=build_market_history_coverage)


class MarketHistoryBatchItemResponse(BaseModel):
    symbol: str
    items: list[OhlcvPointResponse] = Field(default_factory=list)
    coverage: MarketHistoryCoverageResponse = Field(default_factory=build_market_history_coverage)


class MarketHistoryBatchResponse(BaseModel):
    timeframe: str
    items: list[MarketHistoryBatchItemResponse] = Field(default_factory=list)


class RealtimeResponse(BaseModel):
    symbol: str
    timestamp: str | None
    current_price: float | None
    queried_at: str | None = None
    valid_until: str | None = None
    source: str = "unavailable"
    status: Literal["fresh", "stale", "unavailable"] = "unavailable"
    indicators: IndicatorSummaryResponse
    ai_analysis: JsonValue | None
    kline_data: list[OhlcvPointResponse] = Field(default_factory=list)
    timeframe: str | None = None
    type: str | None = None


class KlineTailResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str | None
    current_price: float | None
    queried_at: str | None = None
    valid_until: str | None = None
    status: Literal["fresh", "stale", "unavailable"] = "unavailable"
    kline_data: list[OhlcvPointResponse] = Field(default_factory=list)


class CurrentPriceResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str | None
    current_price: float | None
    source: str = "unavailable"
    received_at: str | None = None
    queried_at: str | None = None
    valid_until: str | None = None
    status: Literal["fresh", "stale", "unavailable"] = "unavailable"
    market: str = "spot"


class CurrentPriceBatchItemResponse(CurrentPriceResponse):
    source: str


class CurrentPriceBatchResponse(BaseModel):
    timeframe: str
    items: list[CurrentPriceBatchItemResponse] = Field(default_factory=list)
