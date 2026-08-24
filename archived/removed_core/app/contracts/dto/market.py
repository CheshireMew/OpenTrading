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


class TradeSetupResponseItem(BaseModel):
    side: str
    entry: float
    target: float
    stop: float
    risk_reward: float
    confidence: int
    risk_amount: float
    entry_time: int
    style: str
    strategy: str
    source: str


class TradeSetupResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str
    current_price: float | None
    setup: TradeSetupResponseItem | None
    reason: str
    source: str


class IndicatorHistoryPoint(BaseModel):
    date: str
    value: float


class MarketIndicatorResponse(BaseModel):
    indicator_id: str
    name: str
    category: str
    unit: str | None
    current_value: float | None
    last_updated: str | None
    data_lag_days: int | None = None
    short_label: str | None = None
    group: str | None = None
    group_label: str | None = None
    group_description: str | None = None
    polarity: str | None = None
    description: str | None = None
    is_scored: bool | None = None
    history: list[IndicatorHistoryPoint]


class DliThresholdsResponse(BaseModel):
    p20: float
    p50: float
    p80: float
    source: str
    sample_size: int


class DliComponentResponse(BaseModel):
    indicator_id: str
    name: str
    short_label: str
    group: str
    group_label: str
    group_description: str | None = None
    weight: float
    effective_weight: float
    polarity: str
    current_value: float | None
    score: float | None
    z_score: float | None
    percentile: float | None
    contribution: float | None
    change_pct: float | None
    last_updated: str | None
    data_lag_days: int | None = None
    missing_reason: str | None = None


class DliHistoryPointResponse(BaseModel):
    date: str
    score: float
    state: str


class DliLiquidityResponse(BaseModel):
    score: int | None
    raw_score: float | None
    score_percentile: float | None
    state: str
    tone: str
    updated_at: str | None
    coverage: float
    methodology: str
    thresholds: DliThresholdsResponse
    components: list[DliComponentResponse]
    history: list[DliHistoryPointResponse] = Field(default_factory=list)
    indicators: list[MarketIndicatorResponse] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)


class ApiStatusResponse(BaseModel):
    status: str
    version: str
    framework: str
    dependencies: str
    timestamp: str


class DisplayCurrencyResponse(BaseModel):
    code: str
    name: str
    symbol: str
    locale: str
    fraction_digits: int


class CurrencyRatesResponse(BaseModel):
    base: str
    rates: dict[str, float]
    supported: list[DisplayCurrencyResponse]
    aliases: dict[str, str] = Field(default_factory=dict)
    updated_at: str
    source: str
    is_fallback: bool = False


class MarketIndexResponse(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None


class MarketSymbolSearchResponse(BaseModel):
    symbol: str
    name: str
    asset_class: str
    market: str
    currency: str
    exchange: str | None = None
    aliases: list[str] = Field(default_factory=list)
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None


class MarketIndexHistoryResponse(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    native_currency: str | None = None
    timeframe: str
    source: str
    price_basis: str = "index"
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None
    is_close_only: bool = False
    count: int
    data: list[OhlcvPointResponse] = Field(default_factory=list)


