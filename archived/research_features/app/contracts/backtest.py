from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.contracts.json_types import JsonValue
from app.contracts.strategy import StrategyIndicatorParamResponse, StrategyTemplateConfigResponse
from app.contracts.backtest_defaults import (
    DEFAULT_FEE_RATE,
    DEFAULT_INITIAL_CASH,
    DEFAULT_PORTFOLIO,
    DEFAULT_RESEARCH,
    DEFAULT_STRATEGY_KEY,
    DEFAULT_TIMEFRAME,
    default_backtest_dates,
)

@dataclass(slots=True)
class StrategyVersionRecord:
    strategy_key: str
    strategy_name: str
    version: int
    template: str
    config: dict[str, Any]
    parameter_space: dict[str, list[Any]] = field(default_factory=dict)
    description: str | None = None
    notes: str | None = None
    version_name: str | None = None
    id: int | None = None
    is_default: bool = False


class BacktestPortfolioConfig(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: list(DEFAULT_PORTFOLIO["symbols"]))
    max_open_trades: int = Field(default=DEFAULT_PORTFOLIO["max_open_trades"], ge=1, le=50)
    position_size_pct: float = Field(default=DEFAULT_PORTFOLIO["position_size_pct"], gt=0, le=100)
    stake_mode: Literal["fixed", "unlimited"] = DEFAULT_PORTFOLIO["stake_mode"]

    @field_validator("symbols", mode="before")
    @classmethod
    def parse_symbols(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [symbol.strip() for symbol in value.split(",") if symbol.strip()]
        return value

    @model_validator(mode="after")
    def validate_portfolio(self) -> "BacktestPortfolioConfig":
        self.symbols = list(dict.fromkeys(symbol.strip() for symbol in self.symbols if symbol.strip()))
        if not self.symbols:
            raise ValueError("至少选择一个交易对")
        if self.stake_mode == "fixed" and self.position_size_pct * self.max_open_trades > 100:
            raise ValueError("固定仓位下，单笔仓位百分比乘以最大持仓数不能超过 100")
        return self


class BacktestResearchConfig(BaseModel):
    slippage_bps: float = Field(default=DEFAULT_RESEARCH["slippage_bps"], ge=0, le=1000)
    funding_rate_daily: float = Field(default=DEFAULT_RESEARCH["funding_rate_daily"], ge=-10, le=10)
    in_sample_ratio: float = Field(default=DEFAULT_RESEARCH["in_sample_ratio"], ge=50, le=100)
    optimize_metric: Literal["sharpe", "profit_pct", "calmar", "profit_factor"] = DEFAULT_RESEARCH["optimize_metric"]
    optimize_trials: int = Field(default=DEFAULT_RESEARCH["optimize_trials"], ge=0, le=500)
    rolling_windows: int = Field(default=DEFAULT_RESEARCH["rolling_windows"], ge=0, le=24)


@dataclass(slots=True)
class BacktestSignalRecord:
    timestamp: datetime
    price: float
    signal: str
    confidence: float
    indicators: dict[str, Any] | None = None
    reasoning: str | None = None


class BacktestTradeRecord(BaseModel):
    opened_at: datetime
    closed_at: datetime | None
    entry_price: float
    exit_price: float | None
    stake_amount: float
    amount: float
    profit_abs: float
    profit_pct: float
    max_drawdown_pct: float | None = None
    duration_minutes: int | None = None
    entry_tag: str | None = None
    exit_reason: str | None = None
    leverage: float = 1.0
    pair: str | None = None
    side: str = "long"


class BacktestEquityPointRecord(BaseModel):
    timestamp: datetime
    equity: float
    pnl_abs: float
    drawdown_pct: float


@dataclass(slots=True)
class BacktestExecutionResult:
    total_candles: int
    signals: list[BacktestSignalRecord] = field(default_factory=list)
    trades: list[BacktestTradeRecord] = field(default_factory=list)
    equity_curve: list[BacktestEquityPointRecord] = field(default_factory=list)
    report: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class BacktestPreviewCommand(BaseModel):
    strategy_key: str = DEFAULT_STRATEGY_KEY
    strategy_version: int | None = None
    timeframe: str = DEFAULT_TIMEFRAME
    start_date: date = Field(default_factory=lambda: default_backtest_dates()[0])
    end_date: date = Field(default_factory=lambda: default_backtest_dates()[1])
    initial_cash: float = Field(default=DEFAULT_INITIAL_CASH, gt=0)
    fee_rate: float = Field(default=DEFAULT_FEE_RATE, ge=0, le=100)
    portfolio: BacktestPortfolioConfig = Field(default_factory=BacktestPortfolioConfig)
    research: BacktestResearchConfig = Field(default_factory=BacktestResearchConfig)

    @model_validator(mode="after")
    def validate_range(self) -> "BacktestPreviewCommand":
        if self.start_date >= self.end_date:
            raise ValueError("开始日期必须早于结束日期")
        if (self.end_date - self.start_date).days < 7:
            raise ValueError("回测区间至少需要 7 天")
        if (self.end_date - self.start_date).days > 3650:
            raise ValueError("回测区间不能超过 3650 天")
        return self

    @property
    def start_datetime(self) -> datetime:
        return datetime.combine(self.start_date, time.min, tzinfo=timezone.utc)

    @property
    def end_datetime(self) -> datetime:
        return datetime.combine(self.end_date, time.max, tzinfo=timezone.utc)


class BacktestStartCommand(BacktestPreviewCommand):
    preview_id: str
    approved_fingerprint: str

    def preview_command(self) -> BacktestPreviewCommand:
        payload = self.model_dump(exclude={"preview_id", "approved_fingerprint"})
        return BacktestPreviewCommand.model_validate(payload)


class PaperStartCommand(BaseModel):
    strategy_key: str = DEFAULT_STRATEGY_KEY
    strategy_version: int | None = None
    timeframe: str = DEFAULT_TIMEFRAME
    initial_cash: float = Field(default=DEFAULT_INITIAL_CASH, gt=0)
    fee_rate: float = Field(default=DEFAULT_FEE_RATE, ge=0, le=100)
    portfolio: BacktestPortfolioConfig = Field(default_factory=BacktestPortfolioConfig)


class CreateIndicatorDefinitionCommand(BaseModel):
    key: str
    name: str
    engine_key: str
    description: str | None = None
    params: list[StrategyIndicatorParamResponse] = Field(default_factory=list)


class CreateStrategyTemplateCommand(BaseModel):
    key: str
    name: str
    category: str
    description: str | None = None
    indicator_keys: list[str] = Field(default_factory=list)
    default_config: StrategyTemplateConfigResponse
    default_parameter_space: dict[str, list[JsonValue]] = Field(default_factory=dict)


class CreateStrategyVersionCommand(BaseModel):
    key: str
    name: str
    template: str
    category: str
    description: str | None = None
    config: StrategyTemplateConfigResponse
    parameter_space: dict[str, list[JsonValue]] = Field(default_factory=dict)
    notes: str | None = None
    make_default: bool = True


class EvolveStrategyFromBacktestCommand(BaseModel):
    backtest_id: int | None = None
    version_name: str | None = None
    notes: str | None = None
    make_default: bool = True
    dry_run: bool = False

    def require_backtest_id(self) -> int:
        if self.backtest_id is None:
            raise ValueError("缺少回测记录 ID")
        return self.backtest_id
