from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.backtest.strategy_config_normalizer import blank_strategy_config
from app.domain.backtest.strategy_contract_options import (
    DIRECTION_OPTIONS,
    GROUP_LOGICS,
    MARKET_TYPE_OPTIONS,
    RULE_OPERATORS,
    TIMEFRAME_OPTIONS,
)
from app.domain.backtest.strategy_rule_tree import build_condition, build_group


def editor_contract() -> dict[str, Any]:
    return {
        "operators": deepcopy(RULE_OPERATORS),
        "group_logics": deepcopy(GROUP_LOGICS),
        "timeframe_options": deepcopy(TIMEFRAME_OPTIONS),
        "market_type_options": deepcopy(MARKET_TYPE_OPTIONS),
        "direction_options": deepcopy(DIRECTION_OPTIONS),
        "blank_condition": build_condition(
            "condition",
            "条件",
            {"kind": "price", "field": "close"},
            "gt",
            {"kind": "value", "value": 0},
        ),
        "blank_group": build_group("group", "条件组", "and", []),
        "blank_config": blank_strategy_config(),
    }
