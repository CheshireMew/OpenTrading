from __future__ import annotations

import json
from copy import deepcopy
from itertools import islice, product
from typing import Any

from app.domain.backtest.strategy_rule_tree import set_by_path


def candidate_strategy_configs(base_config: dict[str, Any], parameter_space: dict[str, list[Any]], optimize_trials: int):
    yield deepcopy(base_config)
    if optimize_trials <= 1 or not parameter_space:
        return
    keys = [key for key, values in parameter_space.items() if values]
    if not keys:
        return
    seen = {json.dumps(base_config, sort_keys=True, default=str)}
    for combo in islice(product(*(parameter_space[key] for key in keys)), max(optimize_trials - 1, 0)):
        candidate = deepcopy(base_config)
        for key, value in zip(keys, combo):
            set_by_path(candidate, key, value)
        signature = json.dumps(candidate, sort_keys=True, default=str)
        if signature in seen:
            continue
        seen.add(signature)
        yield candidate
