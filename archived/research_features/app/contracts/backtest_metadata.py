from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.contracts.backtest import BacktestPortfolioConfig, BacktestResearchConfig


class BacktestPaperPosition(BaseModel):
    symbol: str
    side: str = "long"
    opened_at: str
    entry_price: float
    entry_score: float | None = None
    remaining_amount: float
    remaining_cost: float
    highest_price: float
    lowest_price: float
    last_price: float
    taken_partial_ids: list[str] = Field(default_factory=list)


class BacktestRuntimeState(BaseModel):
    cash_balance: float
    last_processed: dict[str, int | None] = Field(default_factory=dict)
    last_synced_end: int | None = None
    positions: dict[str, BacktestPaperPosition] = Field(default_factory=dict)
    held_bars: int = 0


class BacktestPaperLiveState(BaseModel):
    cash_balance: float
    open_positions: int
    positions: list[BacktestPaperPosition] = Field(default_factory=list)
    last_updated: str
    stop_reason: str | None = None


class BacktestPreviewApproval(BaseModel):
    id: str
    fingerprint: str
    strategy_key: str | None = None
    strategy_version: int | None = None
    timeframe: str | None = None
    symbols: list[str] = Field(default_factory=list)
    markers: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class BacktestRunMetadataCommon(BaseModel):
    schema_version: int | None = None
    execution_model: str | None = None
    engine: str | None = None
    exchange: str | None = None
    market_type: str | None = None
    direction: str | None = None
    strategy_key: str | None = None
    strategy_name: str | None = None
    strategy_version: int | None = None
    strategy_template: str | None = None
    strategy_notes: str | None = None
    symbols: list[str] = Field(default_factory=list)
    execution_symbols: list[str] = Field(default_factory=list)
    price_source: str | None = None
    portfolio_label: str | None = None
    initial_cash: float | None = None
    fee_rate: float | None = None
    fee_ratio: float | None = None
    timeframe: str | None = None
    stake_currency: str | None = None
    portfolio: BacktestPortfolioConfig | None = None
    selected_config: dict[str, Any] = Field(default_factory=dict)
    raw_stats: dict[str, Any] | None = None
    error: str | None = None
    preview: BacktestPreviewApproval | None = None


class BacktestExecutionMetadata(BacktestRunMetadataCommon):
    execution_mode: Literal["backtest"] = "backtest"
    research: dict[str, Any] | BacktestResearchConfig | None = None
    sample_ranges: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    factor_research: dict[str, Any] = Field(default_factory=dict)


class PaperLiveExecutionMetadata(BacktestRunMetadataCommon):
    execution_mode: Literal["paper_live"] = "paper_live"
    runtime_state: BacktestRuntimeState | None = None
    paper_live: BacktestPaperLiveState | None = None
    report: dict[str, Any] | None = None
    factor_research: dict[str, Any] = Field(default_factory=dict)


BacktestRunMetadata = Annotated[
    BacktestExecutionMetadata | PaperLiveExecutionMetadata,
    Field(discriminator="execution_mode"),
]


BACKTEST_RUN_METADATA_ADAPTER: TypeAdapter[BacktestRunMetadata] = TypeAdapter(BacktestRunMetadata)
