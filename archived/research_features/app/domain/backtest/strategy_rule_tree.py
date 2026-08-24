from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.contracts.strategy import StrategyStateBranchResponse, StrategyTemplateConfigResponse


def build_condition(
    node_id: str,
    label: str,
    left: dict[str, Any],
    operator: str,
    right: dict[str, Any],
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "node_type": "condition",
        "label": label,
        "left": left,
        "operator": operator,
        "right": right,
        "enabled": enabled,
    }


def build_group(
    node_id: str,
    label: str,
    logic: str,
    children: list[dict[str, Any]] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "node_type": "group",
        "label": label,
        "logic": logic,
        "enabled": enabled,
        "children": deepcopy(children or []),
    }


def strategy_branch(config: StrategyTemplateConfigResponse, branch_key: str) -> StrategyStateBranchResponse:
    if branch_key == "trend":
        return config.trend
    if branch_key == "range":
        return config.range
    raise ValueError(f"不支持的策略分支: {branch_key}")


def branch_defaults(branch_id: str, label: str, *, enabled: bool = True) -> dict[str, Any]:
    return {
        "id": branch_id,
        "label": label,
        "enabled": enabled,
        "regime": build_group(f"{branch_id}_regime", f"{label}状态", "and", []),
        "long_entry": build_group(f"{branch_id}_long_entry", f"{label}做多入场", "and", [], enabled=True),
        "long_exit": build_group(f"{branch_id}_long_exit", f"{label}做多离场", "or", [], enabled=True),
        "short_entry": build_group(f"{branch_id}_short_entry", f"{label}做空入场", "and", [], enabled=False),
        "short_exit": build_group(f"{branch_id}_short_exit", f"{label}做空离场", "or", [], enabled=False),
    }


def risk_defaults() -> dict[str, Any]:
    return {
        "stoploss": -0.10,
        "roi_targets": [],
        "trade_plan": {
            "enabled": False,
            "stop_multiplier": 1.0,
            "min_stop_pct": 0.01,
            "reward_multiplier": 2.0,
            "atr_indicator": "",
            "support_indicator": "",
            "resistance_indicator": "",
        },
        "trailing": {
            "enabled": False,
            "positive": 0.02,
            "offset": 0.03,
            "only_offset_reached": True,
        },
        "partial_exits": [],
    }


def find_node_in_group(group: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for child in group.get("children") or []:
        if child.get("id") == node_id:
            return child
        if child.get("node_type") == "group":
            nested = find_node_in_group(child, node_id)
            if nested:
                return nested
    return None


def set_by_path(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = payload
    for part in parts[:-1]:
        if isinstance(current, dict) and current.get("node_type") == "group":
            next_node = find_node_in_group(current, part)
            if next_node is None:
                raise ValueError(f"未找到规则路径: {path}")
            current = next_node
            continue
        if isinstance(current, list):
            current = next((item for item in current if item.get("id") == part), None)
            if current is None:
                raise ValueError(f"未找到列表路径: {path}")
            continue
        current = current.setdefault(part, {})
    current[parts[-1]] = value
