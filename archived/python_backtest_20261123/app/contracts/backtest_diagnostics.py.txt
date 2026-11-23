from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class AccountPeriod(BaseModel):
    label: str
    start: int
    end: int
    start_equity: float
    end_equity: float
    return_pct: float | None
    start_mark_time: int
    end_mark_time: int
    partial: bool
    boundary_carried: bool


class DrawdownEpisode(BaseModel):
    peak_time: int
    peak_equity: float
    trough_time: int
    trough_equity: float
    drawdown_pct: float
    recovery_time: int | None
    end_time: int
    recovered: bool
    duration_ms: int
    recovery_duration_ms: int | None


class DrawdownSummary(BaseModel):
    total_episodes: int = 0
    max_drawdown: DrawdownEpisode | None = None
    longest: DrawdownEpisode | None = None
    unrecovered: DrawdownEpisode | None = None
    worst_episodes: list[DrawdownEpisode] = Field(default_factory=list)
    basis: str = ''


class TradeGroupSummary(BaseModel):
    model_config = ConfigDict(extra='allow')
    trades: int
    wins: int
    losses: int
    gross_profit: float
    gross_loss: float
    profit_factor: float | None


class NormalizedTradeStats(TradeGroupSummary):
    principal_per_trade: float
    net_profit: float
    top_1_gross_profit_share_pct: float | None
    top_10_gross_profit_share_pct: float | None
    basis: str


class TradeSnapshot(BaseModel):
    model_config = ConfigDict(extra='allow')
    trade_id: int
    entry_time: int
    side: str
    return_pct: float


class TradeChange(BaseModel):
    kind: Literal['added', 'dropped', 'changed']
    entry_time: int
    side: str
    occurrence: int
    before: TradeSnapshot | None
    after: TradeSnapshot | None
    changed_fields: list[str]


class ComparisonAssessment(BaseModel):
    model_config = ConfigDict(extra='allow')
    issues: list[str]


class BacktestDiagnosticSummary(BaseModel):
    run_id: str
    report: dict[str, Any]
    trade_summary: dict[str, Any]
    median_holding_minutes: float | None
    mean_holding_minutes: float | None
    top_10_gross_profit_share_pct: float | None
    groups: dict[str, dict[str, TradeGroupSummary]]
    basis: str
    equity_kind: Literal['equity', 'execution_equity']
    available: bool
    annual: list[AccountPeriod]
    monthly: list[AccountPeriod]
    drawdown: DrawdownSummary
    normalized: NormalizedTradeStats
    account_basis: str


class BacktestTradeChanges(BaseModel):
    comparison: ComparisonAssessment
    total: int
    offset: int
    items: list[TradeChange]
    unchanged: int
    added: NormalizedTradeStats
    dropped: NormalizedTradeStats
    changed: int
    note: str


class BacktestTradeTimeline(BaseModel):
    run_id: str
    trade: dict[str, Any]
    signals: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    total: int
    offset: int
    items: list[dict[str, Any]]
    lineage: Literal['recorded_events', 'legacy_fills']
    fallback_intervals: list[int] | None = None
    limitations: list[str]
    basis: str
