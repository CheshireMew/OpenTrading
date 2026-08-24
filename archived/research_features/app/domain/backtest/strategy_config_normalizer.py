from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.domain.market.timeframes import timeframe_to_minutes
from app.contracts.strategy import StrategyTemplateConfigResponse
from app.domain.backtest.strategy_contract_options import (
    PRICE_SOURCE_FIELDS,
    RUN_TIMEFRAME_KEYS,
    STRATEGY_CONFIG_FIELDS,
    STRATEGY_IDENTIFIER_PATTERN,
    TIMEFRAME_OPTIONS,
)
from app.domain.backtest.strategy_rule_tree import branch_defaults, build_group, risk_defaults


def execution_defaults() -> dict[str, Any]:
    return {
        "market_type": "spot",
        "direction": "long_only",
    }


def blank_strategy_config() -> dict[str, Any]:
    return _validate_strategy_config(
        {
            "indicators": {},
            "execution": execution_defaults(),
            "regime_priority": ["trend", "range"],
            "trend": branch_defaults("trend", "趋势", enabled=True),
            "range": branch_defaults("range", "区间", enabled=False),
            "risk": risk_defaults(),
        }
    )


def normalize_strategy_identifier(value: Any, label: str) -> str:
    identifier = str(value or "").strip()
    if not STRATEGY_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"{label} 只能使用字母、数字和下划线，且不能以数字开头")
    return identifier


def normalize_optional_strategy_identifier(value: Any, label: str) -> str:
    identifier = str(value or "").strip()
    if not identifier:
        return ""
    return normalize_strategy_identifier(identifier, label)


def explicit_indicator_timeframes(config: dict[str, Any]) -> list[str]:
    normalized: set[str] = set()
    for indicator in (config.get("indicators") or {}).values():
        if not isinstance(indicator, dict):
            continue
        timeframe = normalize_indicator_timeframe(indicator.get("timeframe"))
        if timeframe != "base":
            normalized.add(timeframe)
    return sorted(normalized, key=timeframe_to_minutes)


def preferred_run_timeframe(config: dict[str, Any]) -> str:
    indicator_timeframes = explicit_indicator_timeframes(config)
    return indicator_timeframes[0] if indicator_timeframes else RUN_TIMEFRAME_KEYS[3]


def allowed_run_timeframes(config: dict[str, Any]) -> list[str]:
    indicator_timeframes = explicit_indicator_timeframes(config)
    if not indicator_timeframes:
        return list(RUN_TIMEFRAME_KEYS)
    smallest_minutes = timeframe_to_minutes(indicator_timeframes[0])
    allowed = []
    for timeframe in RUN_TIMEFRAME_KEYS:
        base_minutes = timeframe_to_minutes(timeframe)
        if smallest_minutes >= base_minutes and smallest_minutes % base_minutes == 0:
            allowed.append(timeframe)
    return allowed or [preferred_run_timeframe(config)]


def strategy_runtime_profile(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "indicator_timeframes": explicit_indicator_timeframes(config),
        "allowed_run_timeframes": allowed_run_timeframes(config),
        "preferred_run_timeframe": preferred_run_timeframe(config),
    }


def normalize_indicator_params(params: list[dict[str, Any]], engine_params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    engine_map = {item["key"]: item for item in engine_params}
    normalized = []
    for item in params:
        key = str(item.get("key") or "").strip()
        if not key or key not in engine_map:
            continue
        base = deepcopy(engine_map[key])
        base["label"] = str(item.get("label") or base["label"])
        for field in ("default", "min", "max", "step"):
            if item.get(field) is not None:
                base[field] = item[field]
        normalized.append(base)
    return normalized or deepcopy(engine_params)


def normalize_strategy_config(config: dict[str, Any], default_config: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(default_config or blank_strategy_config())
    if not config:
        return _validate_strategy_config(normalized)
    source_config = config
    unknown_fields = sorted(set(source_config) - STRATEGY_CONFIG_FIELDS)
    if unknown_fields:
        raise ValueError(f"策略配置包含未知字段: {', '.join(unknown_fields)}")
    normalized["indicators"] = normalize_indicators(source_config.get("indicators") or normalized.get("indicators") or {})
    normalized["execution"] = normalize_execution(source_config.get("execution") or normalized.get("execution") or {})
    normalized["regime_priority"] = normalize_regime_priority(
        source_config.get("regime_priority"),
        normalized.get("regime_priority") or ["trend", "range"],
    )
    normalized["trend"] = normalize_branch_node(
        source_config.get("trend"),
        normalized.get("trend") or branch_defaults("trend", "趋势", enabled=True),
        "trend",
        "趋势",
    )
    normalized["range"] = normalize_branch_node(
        source_config.get("range"),
        normalized.get("range") or branch_defaults("range", "区间", enabled=False),
        "range",
        "区间",
    )
    normalized["risk"] = normalize_risk(source_config.get("risk") or {}, normalized.get("risk") or {})
    return _validate_strategy_config(normalized)


def normalize_indicators(indicators: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(indicators, dict):
        raise ValueError("indicators 必须是对象")
    normalized: dict[str, Any] = {}
    for indicator_id, indicator in (indicators or {}).items():
        indicator_key = normalize_strategy_identifier(indicator_id, "指标标识")
        if not isinstance(indicator, dict):
            raise ValueError(f"指标 {indicator_key} 必须是对象")
        unknown_fields = sorted(set(indicator) - {"label", "type", "timeframe", "params"})
        if unknown_fields:
            raise ValueError(f"指标 {indicator_key} 包含未知字段: {', '.join(unknown_fields)}")
        normalized[indicator_key] = {
            "label": str(indicator.get("label") or indicator_key),
            "type": str(indicator.get("type") or "").strip(),
            "timeframe": normalize_indicator_timeframe(indicator.get("timeframe")),
            "params": deepcopy(indicator.get("params") or {}),
        }
    return normalized


def normalize_indicator_timeframe(value: Any) -> str:
    timeframe = str(value or "base").strip()
    valid_keys = {item["key"] for item in TIMEFRAME_OPTIONS}
    if timeframe not in valid_keys:
        raise ValueError(f"不支持的指标周期: {timeframe}")
    return timeframe


def normalize_execution(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("execution 必须是对象")
    unknown_fields = sorted(set(value) - {"market_type", "direction"})
    if unknown_fields:
        raise ValueError(f"execution 包含未知字段: {', '.join(unknown_fields)}")
    market_type = str((value or {}).get("market_type") or "spot").strip()
    direction = str((value or {}).get("direction") or "long_only").strip()
    if market_type not in {"spot", "futures"}:
        raise ValueError(f"不支持的交易市场: {market_type}")
    if direction not in {"long_only", "long_short"}:
        raise ValueError(f"不支持的交易方向: {direction}")
    if market_type == "spot":
        direction = "long_only"
    return {
        "market_type": market_type,
        "direction": direction,
    }


def normalize_regime_priority(value: Any, fallback: list[str] | None = None) -> list[str]:
    if value is None:
        return list(fallback or ["trend", "range"])
    if not isinstance(value, list):
        raise ValueError("regime_priority 必须是列表")
    normalized: list[str] = []
    for item in value:
        branch_key = str(item or "").strip()
        if branch_key not in {"trend", "range"}:
            raise ValueError(f"不支持的策略分支优先级: {branch_key}")
        if branch_key in normalized:
            raise ValueError(f"重复的策略分支优先级: {branch_key}")
        normalized.append(branch_key)
    for item in fallback or ["trend", "range"]:
        if item in {"trend", "range"} and item not in normalized:
            normalized.append(item)
    return normalized or ["trend", "range"]


def normalize_branch_node(branch: dict[str, Any] | None, fallback: dict[str, Any], branch_id: str, label: str) -> dict[str, Any]:
    base = deepcopy(fallback or branch_defaults(branch_id, label))
    source = deepcopy(branch or base)
    if not isinstance(source, dict):
        raise ValueError(f"{branch_id} 分支必须是对象")
    unknown_fields = sorted(set(source) - {"id", "label", "enabled", "regime", "long_entry", "long_exit", "short_entry", "short_exit"})
    if unknown_fields:
        raise ValueError(f"{branch_id} 分支包含未知字段: {', '.join(unknown_fields)}")
    return {
        "id": source.get("id") or base.get("id") or branch_id,
        "label": source.get("label") or base.get("label") or label,
        "enabled": bool(source.get("enabled", base.get("enabled", True))),
        "regime": normalize_group_node(
            source.get("regime"),
            base.get("regime") or build_group(f"{branch_id}_regime", f"{label}状态", "and", []),
            f"{branch_id}_regime",
            f"{label}状态",
        ),
        "long_entry": normalize_group_node(
            source.get("long_entry"),
            base.get("long_entry") or build_group(f"{branch_id}_long_entry", f"{label}做多入场", "and", []),
            f"{branch_id}_long_entry",
            f"{label}做多入场",
        ),
        "long_exit": normalize_group_node(
            source.get("long_exit"),
            base.get("long_exit") or build_group(f"{branch_id}_long_exit", f"{label}做多离场", "or", []),
            f"{branch_id}_long_exit",
            f"{label}做多离场",
        ),
        "short_entry": normalize_group_node(
            source.get("short_entry"),
            base.get("short_entry") or build_group(f"{branch_id}_short_entry", f"{label}做空入场", "and", [], enabled=False),
            f"{branch_id}_short_entry",
            f"{label}做空入场",
        ),
        "short_exit": normalize_group_node(
            source.get("short_exit"),
            base.get("short_exit") or build_group(f"{branch_id}_short_exit", f"{label}做空离场", "or", [], enabled=False),
            f"{branch_id}_short_exit",
            f"{label}做空离场",
        ),
    }


def normalize_group_node(node: dict[str, Any] | None, fallback: dict[str, Any], node_id: str, label: str) -> dict[str, Any]:
    base = deepcopy(fallback or build_group(node_id, label, "and", []))
    source = deepcopy(node or base)
    if not isinstance(source, dict):
        raise ValueError(f"规则组 {node_id} 必须是对象")
    unknown_fields = sorted(set(source) - {"id", "node_type", "label", "logic", "enabled", "children"})
    if unknown_fields:
        raise ValueError(f"规则组 {node_id} 包含未知字段: {', '.join(unknown_fields)}")
    if source.get("node_type") != "group":
        raise ValueError(f"规则组 {node_id} 的 node_type 必须是 group")
    source["id"] = source.get("id") or node_id
    source["label"] = source.get("label") or label
    if source.get("logic") not in {"and", "or"}:
        raise ValueError(f"规则组 {node_id} 的 logic 不支持: {source.get('logic')}")
    if not isinstance(source.get("children") or [], list):
        raise ValueError(f"规则组 {node_id} 的 children 必须是列表")
    source["enabled"] = bool(source.get("enabled", base.get("enabled", True)))
    source["children"] = [normalize_rule_node(child) for child in source.get("children") or []]
    return source


def normalize_rule_node(node: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise ValueError("规则节点必须是对象")
    if (node or {}).get("node_type") == "group":
        return normalize_group_node(
            node,
            build_group(node.get("id") or "group", node.get("label") or "条件组", node.get("logic") or "and", []),
            node.get("id") or "group",
            node.get("label") or "条件组",
        )
    if node.get("node_type") != "condition":
        raise ValueError(f"规则节点 node_type 不支持: {node.get('node_type')}")
    unknown_fields = sorted(set(node) - {"id", "node_type", "label", "left", "operator", "right", "enabled"})
    if unknown_fields:
        raise ValueError(f"规则节点 {node.get('id') or 'condition'} 包含未知字段: {', '.join(unknown_fields)}")
    if node.get("operator") not in {"gt", "gte", "lt", "lte"}:
        raise ValueError(f"不支持的条件操作符: {node.get('operator')}")
    return {
        "id": node.get("id") or "condition",
        "node_type": "condition",
        "label": node.get("label") or "条件",
        "left": normalize_rule_source(node.get("left") or {"kind": "price", "field": "close"}),
        "operator": node.get("operator"),
        "right": normalize_rule_source(node.get("right") or {"kind": "value", "value": 0}),
        "enabled": bool(node.get("enabled", True)),
    }


def normalize_rule_source(source: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError("条件源必须是对象")
    unknown_fields_by_kind = {
        "price": {"kind", "field", "bars_ago"},
        "indicator": {"kind", "indicator", "output", "bars_ago"},
        "value": {"kind", "value", "bars_ago"},
        "indicator_multiplier": {"kind", "indicator", "output", "multiplier", "bars_ago"},
        "indicator_offset": {
            "kind",
            "base_indicator",
            "base_output",
            "offset_indicator",
            "offset_output",
            "offset_multiplier",
            "bars_ago",
        },
    }
    kind = str((source or {}).get("kind") or "").strip()
    if kind not in unknown_fields_by_kind:
        raise ValueError(f"不支持的条件源: {kind}")
    unknown_fields = sorted(set(source) - unknown_fields_by_kind[kind])
    if unknown_fields:
        raise ValueError(f"条件源 {kind} 包含未知字段: {', '.join(unknown_fields)}")
    bars_ago = max(int((source or {}).get("bars_ago", 0) or 0), 0)
    if kind == "price":
        field = str((source or {}).get("field") or "close").strip()
        if field not in PRICE_SOURCE_FIELDS:
            raise ValueError(f"不支持的价格字段: {field}")
        return {"kind": "price", "field": field, "bars_ago": bars_ago}
    if kind == "indicator":
        return {
            "kind": "indicator",
            "indicator": normalize_strategy_identifier(source.get("indicator"), "指标标识"),
            "output": normalize_strategy_identifier(source.get("output") or "value", "指标输出"),
            "bars_ago": bars_ago,
        }
    if kind == "value":
        return {"kind": "value", "value": float(source.get("value", 0)), "bars_ago": bars_ago}
    if kind == "indicator_multiplier":
        return {
            "kind": "indicator_multiplier",
            "indicator": normalize_strategy_identifier(source.get("indicator"), "指标标识"),
            "output": normalize_strategy_identifier(source.get("output") or "value", "指标输出"),
            "multiplier": float(source.get("multiplier", 1.0)),
            "bars_ago": bars_ago,
        }
    if kind == "indicator_offset":
        return {
            "kind": "indicator_offset",
            "base_indicator": normalize_strategy_identifier(source.get("base_indicator"), "基础指标标识"),
            "base_output": normalize_strategy_identifier(source.get("base_output") or "value", "基础指标输出"),
            "offset_indicator": normalize_strategy_identifier(source.get("offset_indicator"), "偏移指标标识"),
            "offset_output": normalize_strategy_identifier(source.get("offset_output") or "value", "偏移指标输出"),
            "offset_multiplier": float(source.get("offset_multiplier", 1.0)),
            "bars_ago": bars_ago,
        }
    raise ValueError(f"不支持的条件源: {kind}")


def normalize_risk(risk: dict[str, Any], base_risk: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(risk, dict):
        raise ValueError("risk 必须是对象")
    unknown_fields = sorted(set(risk) - {"stoploss", "roi_targets", "trailing", "trade_plan", "partial_exits"})
    if unknown_fields:
        raise ValueError(f"risk 包含未知字段: {', '.join(unknown_fields)}")
    normalized = deepcopy(base_risk or risk_defaults())
    normalized["stoploss"] = float(risk.get("stoploss", normalized.get("stoploss", risk_defaults()["stoploss"])))

    roi_targets = risk.get("roi_targets")
    if roi_targets is None:
        roi_targets = normalized.get("roi_targets") or []
    normalized["roi_targets"] = [
        {
            "id": item.get("id") or f"roi_{index}",
            "minutes": int(item.get("minutes", 0)),
            "profit": float(item.get("profit", 0)),
            "enabled": bool(item.get("enabled", True)),
        }
        for index, item in enumerate(roi_targets or [])
    ]

    trailing = risk.get("trailing") or deepcopy(normalized.get("trailing") or {})
    normalized["trailing"] = {
        "enabled": bool(trailing.get("enabled", normalized["trailing"]["enabled"])),
        "positive": float(trailing.get("positive", normalized["trailing"]["positive"])),
        "offset": float(trailing.get("offset", normalized["trailing"]["offset"])),
        "only_offset_reached": bool(trailing.get("only_offset_reached", normalized["trailing"]["only_offset_reached"])),
    }

    trade_plan = risk.get("trade_plan") or deepcopy(normalized.get("trade_plan") or {})
    normalized["trade_plan"] = {
        "enabled": bool(trade_plan.get("enabled", normalized["trade_plan"]["enabled"])),
        "stop_multiplier": float(trade_plan.get("stop_multiplier", normalized["trade_plan"]["stop_multiplier"])),
        "min_stop_pct": float(trade_plan.get("min_stop_pct", normalized["trade_plan"]["min_stop_pct"])),
        "reward_multiplier": float(trade_plan.get("reward_multiplier", normalized["trade_plan"]["reward_multiplier"])),
        "atr_indicator": normalize_optional_strategy_identifier(trade_plan.get("atr_indicator", normalized["trade_plan"]["atr_indicator"] or ""), "ATR 指标标识"),
        "support_indicator": normalize_optional_strategy_identifier(trade_plan.get("support_indicator", normalized["trade_plan"]["support_indicator"] or ""), "支撑指标标识"),
        "resistance_indicator": normalize_optional_strategy_identifier(trade_plan.get("resistance_indicator", normalized["trade_plan"]["resistance_indicator"] or ""), "阻力指标标识"),
    }

    partial_exits = risk.get("partial_exits")
    if partial_exits is None:
        partial_exits = normalized.get("partial_exits") or []
    normalized["partial_exits"] = [
        {
            "id": item.get("id") or f"partial_{index + 1}",
            "profit": float(item.get("profit", 0)),
            "size_pct": float(item.get("size_pct", 0)),
            "enabled": bool(item.get("enabled", True)),
        }
        for index, item in enumerate(partial_exits or [])
    ]
    return normalized


def normalize_parameter_space(parameter_space: dict[str, list[Any]]) -> dict[str, list[Any]]:
    if not isinstance(parameter_space, dict):
        raise ValueError("parameter_space 必须是对象")
    normalized: dict[str, list[Any]] = {}
    for key, values in (parameter_space or {}).items():
        if not isinstance(values, list):
            raise ValueError(f"parameter_space.{key} 必须是列表")
        normalized[str(key)] = list(values)
    return normalized


def normalize_strategy_payload(
    *,
    template_spec: dict[str, Any],
    config: dict[str, Any],
    parameter_space: dict[str, list[Any]] | None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    default_config = template_spec["default_config"]
    default_parameter_space = template_spec["default_parameter_space"]
    normalized_config = normalize_strategy_config(config or {}, default_config)
    normalized_parameter_space = normalize_parameter_space(parameter_space or default_parameter_space)
    return normalized_config, normalized_parameter_space


def normalize_strategy_config_model(
    config: dict[str, Any],
    default_config: dict[str, Any],
) -> StrategyTemplateConfigResponse:
    return _validate_strategy_config_model(normalize_strategy_config(config, default_config))


def _validate_strategy_config(payload: dict[str, Any]) -> dict[str, Any]:
    return _validate_strategy_config_model(payload).model_dump()


def _validate_strategy_config_model(payload: dict[str, Any]) -> StrategyTemplateConfigResponse:
    try:
        return StrategyTemplateConfigResponse.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"策略配置不符合 contract: {exc}") from exc
