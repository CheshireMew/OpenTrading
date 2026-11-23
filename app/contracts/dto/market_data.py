from typing import Literal

from pydantic import BaseModel, ConfigDict


class SignalLabPoint(BaseModel):
    date: str
    value: float


class SignalLabPressurePoint(BaseModel):
    date: str
    score: float


class SignalLabIndicator(BaseModel):
    indicator_id: str
    name: str
    group_label: str
    group_description: str
    unit: str
    current_value: float | None
    last_updated: str | None
    data_lag_days: int | None
    is_stale: bool
    is_scored: bool
    description: str
    history: list[SignalLabPoint]


class SignalLabPressureComponent(BaseModel):
    indicator_id: str
    score: float | None
    z_score: float | None
    percentile: float | None
    effective_weight: float
    contribution: float | None


class SignalLabPressureThresholds(BaseModel):
    p20: float
    p50: float
    p80: float
    sample_size: int


class SignalLabLiquidityResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["signal-lab.liquidity.v1"]
    score: float | None
    raw_score: float | None
    state: str
    tone: str
    coverage: float
    updated_at: str | None
    data_scope_note: str
    thresholds: SignalLabPressureThresholds
    history: list[SignalLabPressurePoint]
    alerts: list[str]
    indicators: list[SignalLabIndicator]
    components: list[SignalLabPressureComponent]


class SignalLabRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignalLabRefreshSummary(BaseModel):
    series_count: int
    row_count: int


class SignalLabRefreshResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["signal-lab.liquidity-refresh.v1"]
    refresh: SignalLabRefreshSummary
    liquidity: SignalLabLiquidityResponse


class SignalLabMarketItem(BaseModel):
    symbol: str
    timeframe: str
    price_source: str
    data_hash: str
    first_opened_at: str | None
    last_opened_at: str | None
    row_count: int


class SignalLabMacroItem(BaseModel):
    indicator_id: str
    name: str
    provider: str
    frequency: str
    start_at: str | None
    end_at: str | None
    row_count: int


class SignalLabInventoryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["signal-lab.database.v1"]
    counts: dict[str, int]
    price_options: list[SignalLabMarketItem]
    market: list[SignalLabMarketItem]
    macro: list[SignalLabMacroItem]


class SignalLabBar(BaseModel):
    date: str
    observed_at: str
    display_price: float | None
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    rsi_14: float | None
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: float | None


class SignalLabCoverage(BaseModel):
    complete: bool | None = None
    missing_dates: list[str] = []
    duplicate_dates: list[str] = []
    incomplete_reasons: list[str] = []


class SignalLabDownload(BaseModel):
    download_url: str | None = None


class SignalLabClassification(BaseModel):
    classification_id: str
    name: str


class SignalLabPriceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal["signal-lab.history.v1"]
    status: Literal["ok", "partial", "ambiguous", "error"]
    records: list[SignalLabBar] = []
    recent_records: list[SignalLabBar] = []
    records_total: int | None = None
    coverage: SignalLabCoverage
    artifact: SignalLabDownload | None = None
    classifications: list[SignalLabClassification] = []
    warnings: list[str]
