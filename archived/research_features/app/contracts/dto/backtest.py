from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.strategy import (
    StrategyConditionNodeResponse,
    StrategyGroupNodeResponse,
    StrategyIndicatorOutputResponse,
    StrategyIndicatorParamResponse,
    StrategyTemplateConfigResponse,
)
from app.contracts.json_types import JsonObject, JsonValue
from app.contracts.backtest import (
    BacktestPortfolioConfig,
    BacktestResearchConfig,
    BacktestEquityPointRecord,
    BacktestTradeRecord,
)
from app.contracts.dto.market import MarketHistoryCoverageResponse, OhlcvPointResponse
from app.contracts.backtest_result import (
    BacktestReportResponse,
    BacktestRunMetadataContractResponse,
)
from app.contracts.backtest_defaults import (
    DEFAULT_FEE_RATE,
    DEFAULT_HISTORY_MODE,
    DEFAULT_INITIAL_CASH,
    DEFAULT_STRATEGY_KEY,
    DEFAULT_TIMEFRAME,
    OPTIMIZE_METRIC_OPTIONS,
    default_backtest_dates,
)


class BacktestStartResponse(BaseModel):
    success: bool
    backtest_id: int
    message: str


class StrategyPreviewMarkerResponse(BaseModel):
    symbol: str
    time: int
    price: float
    kind: Literal["long_entry", "long_exit", "short_entry", "short_exit"]
    side: Literal["long", "short"]
    label: str
    active_regime: str | None = None
    indicators: JsonObject = Field(default_factory=dict)


class StrategyPreviewIndicatorPointResponse(BaseModel):
    time: int
    value: float


class StrategyPreviewIndicatorSeriesResponse(BaseModel):
    symbol: str
    indicator_id: str
    output: str
    label: str
    points: list[StrategyPreviewIndicatorPointResponse] = Field(default_factory=list)


class StrategyPreviewDiagnosticResponse(BaseModel):
    severity: Literal["info", "warning", "critical"]
    title: str
    message: str


class BacktestPreviewResponse(BaseModel):
    preview_id: str
    fingerprint: str
    strategy_key: str
    strategy_name: str
    strategy_version: int
    strategy_template: str
    timeframe: str
    symbols: list[str]
    start_date: str
    end_date: str
    candles: dict[str, list[OhlcvPointResponse]] = Field(default_factory=dict)
    markers: dict[str, list[StrategyPreviewMarkerResponse]] = Field(default_factory=dict)
    indicator_series: dict[str, list[StrategyPreviewIndicatorSeriesResponse]] = Field(default_factory=dict)
    coverage: dict[str, MarketHistoryCoverageResponse] = Field(default_factory=dict)
    diagnostics: list[StrategyPreviewDiagnosticResponse] = Field(default_factory=list)


class PaperStartResponse(BaseModel):
    success: bool
    run_id: int
    message: str


class PaperStopResponse(BaseModel):
    success: bool
    run_id: int
    message: str


class BacktestDeleteResponse(BaseModel):
    success: bool
    run_id: int
    message: str


class BacktestMetricsResponse(BaseModel):
    total_candles: int
    total_signals: int
    buy_signals: int
    sell_signals: int
    hold_signals: int


class BacktestSignalResponse(BaseModel):
    id: int
    timestamp: str | None
    price: float
    signal: str
    confidence: float
    indicators: JsonObject | None = None
    reasoning: str | None = None


class BacktestTradeResponse(BacktestTradeRecord):
    id: int
    pair: str
    opened_at: str | None
    closed_at: str | None


class BacktestEquityPointResponse(BacktestEquityPointRecord):
    id: int
    timestamp: str | None


class BacktestRunResponse(BaseModel):
    id: int
    symbol: str
    timeframe: str
    start_date: str | None
    end_date: str | None
    status: str
    metadata: BacktestRunMetadataContractResponse | None = None
    report: BacktestReportResponse | None = None
    created_at: str | None
    metrics: BacktestMetricsResponse
    signals: list[BacktestSignalResponse] | None = None


class PaginationResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class BacktestDetailResponse(BacktestRunResponse):
    signals: list[BacktestSignalResponse]
    trades: list[BacktestTradeResponse]
    equity_curve: list[BacktestEquityPointResponse]
    pagination: PaginationResponse


class StrategyVersionResponse(BaseModel):
    id: int | None
    version: int
    name: str
    notes: str | None = None
    is_default: bool
    config: StrategyTemplateConfigResponse
    parameter_space: dict[str, list[JsonValue]]
    runtime: "StrategyRunProfileResponse"


class StrategyTemplateCapabilitiesResponse(BaseModel):
    paper: bool = True
    version_editing: bool = True


class StrategyTemplateRuntimeResponse(BaseModel):
    builder_kind: str = "rules"
    capabilities: StrategyTemplateCapabilitiesResponse = Field(
        default_factory=StrategyTemplateCapabilitiesResponse
    )


class StrategyDefinitionResponse(BaseModel):
    key: str
    name: str
    template: str
    category: str
    description: str | None = None
    is_active: bool
    template_runtime: StrategyTemplateRuntimeResponse = Field(
        default_factory=StrategyTemplateRuntimeResponse
    )
    versions: list[StrategyVersionResponse]


class StrategyIndicatorRegistryResponse(BaseModel):
    key: str
    engine: str
    name: str
    description: str | None = None
    outputs: list[StrategyIndicatorOutputResponse]
    params: list[StrategyIndicatorParamResponse]
    is_builtin: bool


class StrategyOperatorResponse(BaseModel):
    key: str
    label: str


class StrategyRunProfileResponse(BaseModel):
    indicator_timeframes: list[str] = Field(default_factory=list)
    allowed_run_timeframes: list[str] = Field(default_factory=list)
    preferred_run_timeframe: str


class StrategyGroupLogicResponse(BaseModel):
    key: str
    label: str


class StrategyIndicatorEngineResponse(BaseModel):
    key: str
    engine: str
    name: str
    description: str | None = None
    outputs: list[StrategyIndicatorOutputResponse]
    params: list[StrategyIndicatorParamResponse]


class StrategyTemplateResponse(BaseModel):
    template: str
    name: str
    category: str
    description: str | None = None
    is_builtin: bool = False
    template_runtime: StrategyTemplateRuntimeResponse = Field(
        default_factory=StrategyTemplateRuntimeResponse
    )
    indicator_keys: list[str] = Field(default_factory=list)
    indicator_registry: list[StrategyIndicatorRegistryResponse]
    operators: list[StrategyOperatorResponse]
    group_logics: list[StrategyGroupLogicResponse]
    default_config: StrategyTemplateConfigResponse
    default_parameter_space: dict[str, list[JsonValue]]


class BacktestRunDefaultsResponse(BaseModel):
    strategy_key: str = DEFAULT_STRATEGY_KEY
    timeframe: str = DEFAULT_TIMEFRAME
    start_date: str = Field(
        default_factory=lambda: default_backtest_dates()[0].isoformat()
    )
    end_date: str = Field(
        default_factory=lambda: default_backtest_dates()[1].isoformat()
    )
    initial_cash: float = DEFAULT_INITIAL_CASH
    fee_rate: float = DEFAULT_FEE_RATE
    portfolio: BacktestPortfolioConfig = Field(
        default_factory=BacktestPortfolioConfig
    )
    research: BacktestResearchConfig = Field(default_factory=BacktestResearchConfig)
    history_mode: Literal["backtest", "paper"] = DEFAULT_HISTORY_MODE
    optimize_metric_options: list[StrategyOperatorResponse] = Field(
        default_factory=lambda: [
            StrategyOperatorResponse(**item) for item in OPTIMIZE_METRIC_OPTIONS
        ]
    )


class StrategyEditorContractResponse(BaseModel):
    operators: list[StrategyOperatorResponse]
    group_logics: list[StrategyGroupLogicResponse]
    timeframe_options: list[StrategyOperatorResponse]
    market_type_options: list[StrategyOperatorResponse]
    direction_options: list[StrategyOperatorResponse]
    blank_condition: StrategyConditionNodeResponse
    blank_group: StrategyGroupNodeResponse
    blank_config: StrategyTemplateConfigResponse
    run_defaults: BacktestRunDefaultsResponse


class StrategyEvolutionDefectResponse(BaseModel):
    key: str
    severity: Literal["info", "warning", "critical"]
    title: str
    evidence: list[str] = Field(default_factory=list)
    recommendation: str


class StrategyEvolutionChangeResponse(BaseModel):
    path: str
    before: JsonValue | None = None
    after: JsonValue | None = None
    reason: str


class StrategyEvolutionResponse(BaseModel):
    source_backtest_id: int
    strategy_key: str
    source_version: int | None = None
    created: bool
    message: str
    defects: list[StrategyEvolutionDefectResponse] = Field(default_factory=list)
    changes: list[StrategyEvolutionChangeResponse] = Field(default_factory=list)
    evolved_version: StrategyVersionResponse | None = None
    base_config: StrategyTemplateConfigResponse
    evolved_config: StrategyTemplateConfigResponse
