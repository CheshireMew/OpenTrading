from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.json_types import JsonValue


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
    timestamp: str
    current_price: float
    indicators: IndicatorSummaryResponse
    ai_analysis: JsonValue | None
    kline_data: list[OhlcvPointResponse] = Field(default_factory=list)
    timeframe: str | None = None
    type: str | None = None


class KlineTailResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str
    current_price: float | None
    kline_data: list[OhlcvPointResponse] = Field(default_factory=list)


class CurrentPriceResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str
    current_price: float | None


class CurrentPriceBatchItemResponse(CurrentPriceResponse):
    source: str


class CurrentPriceBatchResponse(BaseModel):
    timeframe: str
    items: list[CurrentPriceBatchItemResponse] = Field(default_factory=list)
