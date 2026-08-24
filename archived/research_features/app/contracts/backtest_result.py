from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.contracts.backtest import BacktestPortfolioConfig, BacktestResearchConfig
from app.contracts.backtest_metadata import (
    BacktestExecutionMetadata,
    BacktestPaperLiveState,
    BacktestPaperPosition,
    BacktestPreviewApproval,
    BacktestRuntimeState,
    PaperLiveExecutionMetadata,
)
from app.contracts.json_types import JsonObject
from app.contracts.strategy import StrategyTemplateConfigResponse

class BacktestReportSnapshotResponse(BaseModel):
    profit_pct: float | None = None
    profit_abs: float | None = None
    final_balance: float | None = None
    max_drawdown_pct: float | None = None
    sharpe: float | None = None
    calmar: float | None = None
    profit_factor: float | None = None
    win_rate: float | None = None
    total_trades: int | None = None


class BacktestDateRangeResponse(BaseModel):
    start: str
    end: str


class BacktestPairBreakdownResponse(BaseModel):
    pair: str
    trades: int
    profit_abs: float
    profit_pct: float
    win_rate: float


class BacktestStrategySummaryResponse(BaseModel):
    key: str
    name: str
    version: int
    template: str


class BacktestPortfolioSummaryResponse(BacktestPortfolioConfig):
    stake_currency: str | None = None


class BacktestOptimizationTrialResponse(BaseModel):
    trial: int
    score: float | None = None
    config: StrategyTemplateConfigResponse
    report: BacktestReportSnapshotResponse | None = None


class BacktestOptimizationSummaryResponse(BaseModel):
    metric: str
    trial_count: int
    best_score: float | None = None
    best_config: StrategyTemplateConfigResponse | None = None
    trials: list[BacktestOptimizationTrialResponse] = Field(default_factory=list)


class BacktestIterationSummaryResponse(BaseModel):
    range: BacktestDateRangeResponse | None = None
    config: StrategyTemplateConfigResponse
    report: BacktestReportSnapshotResponse | None = None


class BacktestRollingWindowResponse(BaseModel):
    index: int
    train: BacktestDateRangeResponse | None = None
    test: BacktestDateRangeResponse
    config: StrategyTemplateConfigResponse
    optimization: BacktestOptimizationSummaryResponse | None = None
    report: BacktestReportSnapshotResponse | None = None


class BacktestResearchReportResponse(BaseModel):
    selected_config: StrategyTemplateConfigResponse | None = None
    in_sample_ratio: float
    slippage_bps: float
    funding_rate_daily: float
    optimization: BacktestOptimizationSummaryResponse | None = None
    in_sample: BacktestIterationSummaryResponse | None = None
    out_of_sample: BacktestIterationSummaryResponse | None = None
    rolling_windows: list[BacktestRollingWindowResponse] = Field(default_factory=list)


class BacktestReportResponse(BaseModel):
    initial_cash: float
    final_balance: float
    profit_abs: float
    profit_pct: float
    annualized_return_pct: float | None = None
    max_drawdown_pct: float
    sharpe: float | None = None
    sortino: float | None = None
    calmar: float | None = None
    profit_factor: float | None = None
    expectancy_ratio: float | None = None
    win_rate: float
    total_trades: int
    wins: int
    losses: int
    draws: int
    avg_trade_pct: float | None = None
    avg_trade_duration_minutes: int | None = None
    best_trade_pct: float | None = None
    worst_trade_pct: float | None = None
    pair_breakdown: list[BacktestPairBreakdownResponse] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    timeframe: str | None = None
    strategy: BacktestStrategySummaryResponse | None = None
    portfolio: BacktestPortfolioSummaryResponse | None = None
    research: BacktestResearchReportResponse | None = None


class BacktestSampleRangesResponse(BaseModel):
    requested: BacktestDateRangeResponse | None = None
    displayed: BacktestDateRangeResponse | None = None
    in_sample: BacktestDateRangeResponse | None = None
    out_of_sample: BacktestDateRangeResponse | None = None


class BacktestPaperPositionResponse(BacktestPaperPosition):
    pass


class BacktestRuntimeStateResponse(BacktestRuntimeState):
    positions: dict[str, BacktestPaperPositionResponse] = Field(default_factory=dict)


class BacktestPaperLiveResponse(BacktestPaperLiveState):
    positions: list[BacktestPaperPositionResponse] = Field(default_factory=list)


class BacktestPreviewApprovalResponse(BacktestPreviewApproval):
    markers: dict[str, list[JsonObject]] = Field(default_factory=dict)
    diagnostics: list[JsonObject] = Field(default_factory=list)


class BacktestExecutionMetadataResponse(BacktestExecutionMetadata):
    selected_config: JsonObject = Field(default_factory=dict)
    raw_stats: BacktestReportSnapshotResponse | None = None
    preview: BacktestPreviewApprovalResponse | None = None
    execution_mode: Literal["backtest"] = "backtest"
    research: BacktestResearchReportResponse | BacktestResearchConfig | None = None
    sample_ranges: BacktestSampleRangesResponse | None = None
    report: BacktestReportResponse | None = None
    factor_research: JsonObject = Field(default_factory=dict)


class PaperLiveExecutionMetadataResponse(PaperLiveExecutionMetadata):
    selected_config: JsonObject = Field(default_factory=dict)
    raw_stats: BacktestReportSnapshotResponse | None = None
    preview: BacktestPreviewApprovalResponse | None = None
    execution_mode: Literal["paper_live"] = "paper_live"
    runtime_state: BacktestRuntimeStateResponse | None = None
    paper_live: BacktestPaperLiveResponse | None = None
    report: BacktestReportResponse | None = None
    factor_research: JsonObject = Field(default_factory=dict)


BacktestRunMetadataContractResponse = Annotated[
    BacktestExecutionMetadataResponse | PaperLiveExecutionMetadataResponse,
    Field(discriminator="execution_mode"),
]
