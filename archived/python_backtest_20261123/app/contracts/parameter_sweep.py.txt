"""User-facing parameter grids; no research-plan boilerplate is required."""
from decimal import Decimal
from itertools import product
from math import prod
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.contracts.local_backtest import LocalBacktestCommand


class ParameterRange(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    start: float
    end: float
    step: float = Field(gt=0)

    def values(self):
        lo, hi, step = map(lambda v: Decimal(str(v)), (self.start, self.end, self.step))
        if hi < lo:
            raise ValueError('参数范围的结束值不能小于开始值')
        count = int((hi-lo)//step)+1
        if count > 512:
            raise ValueError('单个参数最多512个取值，请增大步长')
        return [int(x) if x == x.to_integral() else float(x) for x in (lo+i*step for i in range(count))]


class ParameterSweepCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    title: str = Field(min_length=1, max_length=160)
    base: LocalBacktestCommand
    axes: dict[str, list[Any] | ParameterRange] = Field(default_factory=dict)
    source_run: str | None = None
    parent: str | None = None
    max_runs: int = Field(default=512, ge=1, le=512)

    def expand(self):
        axes = {}
        for key, axis in self.axes.items():
            if key not in {'timeframe', 'position_pct', 'execution_timeframe', 'intrabar_profit_protection'} and not key.startswith('parameters.'):
                raise ValueError(f'不支持的比较参数：{key}')
            values = axis.values() if isinstance(axis, ParameterRange) else axis
            if not values or any(type(v) not in (int, float, bool, str) and not (key == 'execution_timeframe' and v is None) for v in values):
                raise ValueError(f'{key} 必须提供非空的数字、布尔值或文字列表')
            # Duplicates do not create redundant simulations; bool and 1 differ.
            unique = {(type(v).__name__, str(v)):v for v in values}
            axes[key] = list(unique.values())
        count = prod(map(len, axes.values()))
        if count > self.max_runs:
            raise ValueError(f'共{count}组，超过本批上限{self.max_runs}组，请缩小范围')
        commands = []
        for values in product(*axes.values()):
            cfg = self.base.model_dump(mode='json')
            for key, value in zip(axes, values):
                if not key.startswith('parameters.'):
                    cfg[key] = value
                else:
                    cfg['parameters'][key.removeprefix('parameters.')] = value
            commands.append(LocalBacktestCommand.model_validate(cfg))
        return axes, commands


from app.contracts.local_backtest import LocalBacktestPreview, CachedInterval, LocalBacktestStrategy


class SweepDataPreview(LocalBacktestPreview):
    case: str


class ParameterSweepPreview(BaseModel):
    count: int
    new_runs: int
    reused_runs: int
    axes: dict[str, list[Any]]
    fixed_parameters: dict[str, Any]
    warnings: list[str]
    data_previews: list[SweepDataPreview] = Field(default_factory=list)
    comparable_intervals: list[CachedInterval] = Field(default_factory=list)


class ParameterSweepItem(BaseModel):
    case: str
    name: str
    parameters: dict[str, Any]
    timeframe: str
    run_id: str | None
    status: str
    progress: float
    report: dict[str, Any] | None
    error: str | None
    chart_path: str | None
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class ParameterSweepView(BaseModel):
    id: str
    title: str
    created_at: str
    status: str
    total: int
    counts: dict[str, int]
    progress: float
    request: ParameterSweepCommand
    axes: dict[str, list[Any]]
    warnings: list[str]
    path: str
    items: list[ParameterSweepItem]
    offset: int
    filtered_total: int
    strategy: LocalBacktestStrategy | None = None


class ParameterSweepList(BaseModel):
    items: list[dict[str, Any]]
    total: int


class ParameterSweepAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['resume', 'cancel']


class ParameterSweepEffects(BaseModel):
    effects: list[dict[str, Any]]
