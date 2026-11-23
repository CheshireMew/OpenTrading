"""A bounded research question and explicit cases, not a parameter optimizer."""
from typing import Literal
from itertools import product
from math import prod
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.contracts.local_backtest import LocalBacktestCommand


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Question(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    text: str = Field(min_length=1)


class StudyCase(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    period: str = Field(min_length=1)
    role: Literal["exploration", "selection", "validation", "test"]
    previously_seen: bool
    command: LocalBacktestCommand
    reuse_run: str | None = None


class StudyPlan(Strict):
    title: str = Field(min_length=1)
    family: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    decision_rule: str = Field(min_length=1)
    stop_rule: str = Field(min_length=1)
    parent: str | None = None
    change_reason: str = Field(min_length=1)
    questions: list[Question] = Field(min_length=1)
    cases: list[StudyCase] = Field(min_length=1)
    max_new_runs: int = Field(ge=0)

    @model_validator(mode="after")
    def unique(self):
        for name in ("questions", "cases"):
            identifiers = [v.id for v in getattr(self, name)]
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{name} 的 id 重复")
        if sum(c.reuse_run is None for c in self.cases) > self.max_new_runs:
            raise ValueError("新回测数量超过 max_new_runs；先缩小问题或明确修改计划")
        order = {'selection': 0, 'validation': 1, 'test': 2}
        for first in self.cases:
            for later in self.cases:
                if (first.role in order and later.role in order and order[first.role] < order[later.role]
                        and first.command.symbol == later.command.symbol
                        and first.command.end > later.command.start):
                    raise ValueError('同一标的的选择、验证、测试应按时间向前且不重叠；描述性全期对比请用 exploration')
        return self


class StudyAnswer(Strict):
    question: str
    conclusion: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    scope: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    decision: Literal["keep", "reject", "inconclusive"]


class StudyPeriod(Strict):
    name: str = Field(min_length=1)
    start: str
    end: str
    role: Literal['exploration', 'selection', 'validation', 'test']
    previously_seen: bool


class StudyMatrix(Strict):
    """Compact authoring format; expanded and frozen before any queue submission."""
    title: str
    family: str
    objective: str
    decision_rule: str
    stop_rule: str
    change_reason: str
    parent: str | None = None
    questions: list[Question]
    max_new_runs: int = Field(ge=0)
    base: LocalBacktestCommand
    axes: dict[str, list[str | int | float | bool]]
    periods: list[StudyPeriod] = Field(min_length=1)

    def expand(self):
        if any(not v for v in self.axes.values()):
            raise ValueError('参数取值列表不能为空')
        count = prod(len(v) for v in self.axes.values()) * len(self.periods)
        if count > self.max_new_runs:
            raise ValueError(f'展开后 {count} 个案例，超过 max_new_runs={self.max_new_runs}')
        keys, cases = list(self.axes), []
        for index, values in enumerate(product(*self.axes.values())):
            config = self.base.model_dump(mode='json')
            for key, value in zip(keys, values):
                if key.startswith('parameters.'):
                    config['parameters'][key.removeprefix('parameters.')] = value
                elif key in {'symbol', 'timeframe'}:
                    config[key] = value
                else:
                    raise ValueError(f'不支持的实验因素：{key}；资金等约定在 base 中明确固定')
            label = ', '.join(f'{k}={v}' for k, v in zip(keys, values)) or '基准'
            for period_index, period in enumerate(self.periods):
                cases.append(dict(id=f'v{index + 1}-p{period_index + 1}', name=f'{label} · {period.name}',
                                  variant=f'v{index + 1}', period=period.name, role=period.role,
                                  previously_seen=period.previously_seen,
                                  command={**config, 'parameters': dict(config['parameters']),
                                           'start': period.start, 'end': period.end}))
        return StudyPlan.model_validate({**self.model_dump(exclude={'base', 'axes', 'periods'}), 'cases': cases})


def parse_plan(payload):
    if 'base' in payload:
        return StudyMatrix.model_validate(payload).expand()
    return StudyPlan.model_validate(payload)
