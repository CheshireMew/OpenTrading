from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrategyContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyIndicatorOutputResponse(StrategyContractModel):
    key: str
    label: str


class StrategyIndicatorParamResponse(StrategyContractModel):
    key: str
    label: str
    type: Literal["int", "float", "bool"]
    default: float | bool
    min: float | None = None
    max: float | None = None
    step: float | None = None


class StrategyPriceSourceResponse(StrategyContractModel):
    kind: Literal["price"] = "price"
    field: Literal["open", "high", "low", "close", "volume"] = "close"
    bars_ago: int = 0


class StrategyIndicatorSourceResponse(StrategyContractModel):
    kind: Literal["indicator"] = "indicator"
    indicator: str
    output: str = "value"
    bars_ago: int = 0


class StrategyValueSourceResponse(StrategyContractModel):
    kind: Literal["value"] = "value"
    value: float
    bars_ago: int = 0


class StrategyIndicatorMultiplierSourceResponse(StrategyContractModel):
    kind: Literal["indicator_multiplier"] = "indicator_multiplier"
    indicator: str
    output: str = "value"
    multiplier: float = 1.0
    bars_ago: int = 0


class StrategyIndicatorOffsetSourceResponse(StrategyContractModel):
    kind: Literal["indicator_offset"] = "indicator_offset"
    base_indicator: str
    base_output: str = "value"
    offset_indicator: str
    offset_output: str = "value"
    offset_multiplier: float = 1.0
    bars_ago: int = 0


StrategyRuleSourceResponse = Annotated[
    StrategyPriceSourceResponse
    | StrategyIndicatorSourceResponse
    | StrategyValueSourceResponse
    | StrategyIndicatorMultiplierSourceResponse
    | StrategyIndicatorOffsetSourceResponse,
    Field(discriminator="kind"),
]


class StrategyConditionNodeResponse(StrategyContractModel):
    id: str
    node_type: Literal["condition"] = "condition"
    label: str
    left: StrategyRuleSourceResponse
    operator: Literal["gt", "gte", "lt", "lte"]
    right: StrategyRuleSourceResponse
    enabled: bool = True


class StrategyGroupNodeResponse(StrategyContractModel):
    id: str
    node_type: Literal["group"] = "group"
    label: str
    logic: Literal["and", "or"]
    enabled: bool = True
    children: list["StrategyConditionNodeResponse | StrategyGroupNodeResponse"] = Field(
        default_factory=list
    )


class StrategyIndicatorConfigResponse(StrategyContractModel):
    label: str
    type: str
    timeframe: str = "base"
    params: dict[str, float | bool] = Field(default_factory=dict)


class StrategyExecutionConfigResponse(StrategyContractModel):
    market_type: Literal["spot", "futures"] = "spot"
    direction: Literal["long_only", "long_short"] = "long_only"


class StrategyStateBranchResponse(StrategyContractModel):
    id: str
    label: str
    enabled: bool = True
    regime: StrategyGroupNodeResponse
    long_entry: StrategyGroupNodeResponse
    long_exit: StrategyGroupNodeResponse
    short_entry: StrategyGroupNodeResponse
    short_exit: StrategyGroupNodeResponse


class StrategyRoiTargetResponse(StrategyContractModel):
    id: str
    minutes: int
    profit: float
    enabled: bool = True


class StrategyPartialExitResponse(StrategyContractModel):
    id: str
    profit: float
    size_pct: float
    enabled: bool = True


class StrategyTrailingConfigResponse(StrategyContractModel):
    enabled: bool = False
    positive: float
    offset: float
    only_offset_reached: bool = True


class StrategyTradePlanConfigResponse(StrategyContractModel):
    enabled: bool = False
    stop_multiplier: float = 1.0
    min_stop_pct: float = 0.01
    reward_multiplier: float = 2.0
    atr_indicator: str = ""
    support_indicator: str = ""
    resistance_indicator: str = ""


class StrategyRiskConfigResponse(StrategyContractModel):
    stoploss: float
    roi_targets: list[StrategyRoiTargetResponse] = Field(default_factory=list)
    trailing: StrategyTrailingConfigResponse
    partial_exits: list[StrategyPartialExitResponse] = Field(default_factory=list)
    trade_plan: StrategyTradePlanConfigResponse = Field(
        default_factory=StrategyTradePlanConfigResponse
    )


class StrategyTemplateConfigResponse(StrategyContractModel):
    indicators: dict[str, StrategyIndicatorConfigResponse] = Field(default_factory=dict)
    execution: StrategyExecutionConfigResponse
    regime_priority: list[Literal["trend", "range"]] = Field(
        default_factory=lambda: ["trend", "range"]
    )
    trend: StrategyStateBranchResponse
    range: StrategyStateBranchResponse
    risk: StrategyRiskConfigResponse


StrategyGroupNodeResponse.model_rebuild()
