from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LocalBacktestCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    strategy: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    symbol: str = "BTC/USDT"
    timeframe: Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"] = "1h"
    start: datetime
    end: datetime
    initial_cash: float = Field(default=10000, gt=0)
    position_pct: float = Field(default=100, gt=0, le=100)
    data_gap_policy: Literal['reject', 'observed_bars'] = 'reject'
    execution_timeframe: Literal['1m', '5m', '15m', '30m', '1h'] | None = None
    intrabar_profit_protection: bool = False
    execution_gap_policy: Literal['reject', 'coarse_fallback'] = 'coarse_fallback'

    @model_validator(mode="after")
    def dates(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("起止时间必须包含时区，例如 +00:00")
        self.start = self.start.astimezone(timezone.utc)
        self.end = self.end.astimezone(timezone.utc)
        if self.end <= self.start:
            raise ValueError("结束时间必须晚于开始时间")
        from app.domain.market.constants import timeframe_to_milliseconds
        if self.execution_timeframe:
            smaller=timeframe_to_milliseconds(self.execution_timeframe)
            larger=timeframe_to_milliseconds(self.timeframe)
            if smaller>=larger or larger%smaller:
                raise ValueError('成交周期必须小于信号周期，并能整除信号周期')
        elif self.intrabar_profit_protection:
            raise ValueError('盘中利润保护必须指定细周期行情')
        return self


class ParameterOption(BaseModel):
    value: Any
    label: str


class ParameterCondition(BaseModel):
    parameter: str
    operator: Literal['eq', 'ne', 'in', 'gt'] = 'eq'
    value: Any


class WarmupTerm(BaseModel):
    kind: Literal['ema', 'rma', 'window']
    period: int | str
    extra_bars: int | str = 0
    enabled_when: list[ParameterCondition] = Field(default_factory=list)


class WarmupRule(BaseModel):
    version: Literal['1'] = '1'
    seed_weight_tolerance: float = Field(default=1e-8, gt=0, lt=1)
    minimum_bars: int = Field(default=1, ge=0)
    terms: list[WarmupTerm] = Field(min_length=1)
    explanation: str


class LocalBacktestParameter(BaseModel):
    type: Literal["int", "float", "bool", "str"]
    default: Any
    min: float | None = None
    max: float | None = None
    label: str = ""
    options: list[ParameterOption] = Field(default_factory=list)
    unit: str = ''
    enabled_when: list[ParameterCondition] = Field(default_factory=list)
    help: str = ''


class ParameterConstraint(BaseModel):
    parameter: str
    operator: Literal['lt', 'le', 'eq', 'gt', 'integer']
    other_parameter: str | None = None
    value: Any = None
    enabled_when: list[ParameterCondition] = Field(default_factory=list)
    message: str


class LocalBacktestStrategy(BaseModel):
    id: str
    name: str
    description: str
    api_version: str
    warmup_bars: int
    parameters: dict[str, LocalBacktestParameter]
    error: str | None = None
    rules: list[str] = Field(default_factory=list)
    warmup_rule: WarmupRule | None = None
    parameter_constraints: list[ParameterConstraint] = Field(default_factory=list)


class CachedInterval(BaseModel):
    start_ms: int
    end_ms: int


class DataCoverage(BaseModel):
    timeframe: str
    required_start_ms: int
    required_end_ms: int
    first_cached_ms: int | None
    last_cached_close_ms: int | None
    expected_bars: int
    cached_bars: int
    missing_bars: int
    complete_intervals: list[CachedInterval]


class LocalBacktestPreview(BaseModel):
    config: dict[str, Any]
    warmup_bars: int
    warmup_explanation: str
    rules_summary: list[str]
    signal_data: DataCoverage
    execution_data: DataCoverage | None = None
    comparable_intervals: list[CachedInterval]
    warnings: list[str]


class LocalBacktestCatalog(BaseModel):
    strategies: list[LocalBacktestStrategy]
    symbols: list[str]
    timeframes: dict[str, list[str]]


class LocalBacktestRun(BaseModel):
    id: str
    status: str
    progress: float
    created_at: str
    parent_id: str | None = None
    archived: bool = False
    error: str | None = None
    config: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] | None = None
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    progress_detail: dict[str, Any] = Field(default_factory=dict)
    resume_available: bool = False


class LocalBacktestRuns(BaseModel):
    items: list[LocalBacktestRun]
    total: int


class LocalBacktestRecords(BaseModel):
    items: list[dict[str, Any]]
    total: int
    offset: int


class LocalBacktestExport(BaseModel):
    filename: str
    content: str
    media_type: str


class LocalBacktestAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
