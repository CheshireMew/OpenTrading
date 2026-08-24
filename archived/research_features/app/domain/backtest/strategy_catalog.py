from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.backtest.indicator_engines import INDICATOR_ENGINES
from app.domain.backtest.scripted_templates import get_template_runtime
from app.domain.backtest.strategy_config_normalizer import (
    blank_strategy_config,
    normalize_indicator_params,
    normalize_parameter_space,
    normalize_strategy_config,
    normalize_strategy_identifier,
)
from app.domain.backtest.strategy_definitions import BUILTIN_TEMPLATE_DEFINITIONS
from app.domain.backtest.strategy_editor_contract import editor_contract


def get_indicator_engine_catalog() -> list[dict[str, Any]]:
    return [
        {"key": key, **engine.catalog_entry()}
        for key, engine in INDICATOR_ENGINES.items()
    ]


def get_builtin_indicator_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "engine": key,
            "is_builtin": True,
            **engine.catalog_entry(),
        }
        for key, engine in INDICATOR_ENGINES.items()
    ]


def normalize_custom_indicator_definition(
    *,
    key: str,
    name: str,
    engine_key: str,
    description: str | None,
    params: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    normalized_key = normalize_strategy_identifier(key, "指标标识")
    if normalized_key in INDICATOR_ENGINES:
        raise ValueError("该指标标识已被内置指标占用")
    engine = INDICATOR_ENGINES.get(engine_key)
    if not engine:
        raise ValueError("不支持的指标引擎")
    engine_spec = engine.catalog_entry()
    return {
        "key": normalized_key,
        "engine": engine_key,
        "name": name.strip() or normalized_key,
        "description": description.strip() if description else None,
        "outputs": deepcopy(engine_spec["outputs"]),
        "params": normalize_indicator_params(
            params or deepcopy(engine_spec["params"]),
            engine_spec["params"],
        ),
        "is_builtin": False,
    }


def get_indicator_catalog(custom_indicators: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    catalog = {item["key"]: item for item in get_builtin_indicator_catalog()}
    for item in custom_indicators or []:
        catalog[item["key"]] = deepcopy(item)
    return sorted(
        catalog.values(),
        key=lambda item: (item.get("is_builtin") is False, item["name"].lower()),
    )


def get_indicator_registry_map(custom_indicators: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in get_indicator_catalog(custom_indicators)}


def get_builtin_template_catalog(custom_indicators: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    indicator_map = get_indicator_registry_map(custom_indicators)
    contract = editor_contract()
    return [
        _template_payload(template_key, spec, indicator_map, contract, is_builtin=True)
        for template_key, spec in BUILTIN_TEMPLATE_DEFINITIONS.items()
    ]


def normalize_custom_template_definition(
    *,
    key: str,
    name: str,
    category: str,
    description: str | None,
    indicator_keys: list[str],
    default_config: dict[str, Any],
    default_parameter_space: dict[str, list[Any]] | None,
    custom_indicators: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_key = normalize_strategy_identifier(key, "模板标识")
    if normalized_key in BUILTIN_TEMPLATE_DEFINITIONS:
        raise ValueError("该模板标识已被内置模板占用")
    indicator_map = get_indicator_registry_map(custom_indicators)
    merged_indicator_keys = list(
        dict.fromkeys(
            [
                *indicator_keys,
                *[
                    item.get("type")
                    for item in (default_config.get("indicators") or {}).values()
                    if item.get("type")
                ],
            ]
        )
    )
    missing = [
        indicator_key
        for indicator_key in merged_indicator_keys
        if indicator_key not in indicator_map
    ]
    if missing:
        raise ValueError(f"存在未注册的指标: {', '.join(missing)}")
    return {
        "key": normalized_key,
        "name": name.strip() or normalized_key,
        "category": category.strip() or "custom",
        "description": description.strip() if description else None,
        "indicator_keys": merged_indicator_keys,
        "default_config": normalize_strategy_config(default_config, blank_strategy_config()),
        "default_parameter_space": normalize_parameter_space(default_parameter_space or {}),
        "is_builtin": False,
    }


def get_template_catalog(
    *,
    custom_indicators: list[dict[str, Any]] | None = None,
    custom_templates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    indicator_map = get_indicator_registry_map(custom_indicators)
    contract = editor_contract()
    catalog = {item["template"]: item for item in get_builtin_template_catalog(custom_indicators)}
    for item in custom_templates or []:
        catalog[item["key"]] = _template_payload(
            item["key"],
            {
                "name": item["name"],
                "category": item["category"],
                "description": item.get("description"),
                "indicator_keys": list(item.get("indicator_keys") or []),
                "config": deepcopy(item.get("default_config") or {}),
                "parameter_space": deepcopy(item.get("default_parameter_space") or {}),
            },
            indicator_map,
            contract,
            is_builtin=False,
        )
    return sorted(
        catalog.values(),
        key=lambda item: (item.get("is_builtin") is False, item["name"].lower()),
    )


def get_template_spec(
    template: str,
    *,
    custom_indicators: list[dict[str, Any]] | None = None,
    custom_templates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    for item in get_template_catalog(
        custom_indicators=custom_indicators,
        custom_templates=custom_templates,
    ):
        if item["template"] == template:
            return item
    raise ValueError(f"不支持的策略模板: {template}")


def get_template_runtime_contract(template: str) -> dict[str, Any]:
    return get_template_runtime(template)


def get_builtin_strategy_definitions() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for template_key, spec in BUILTIN_TEMPLATE_DEFINITIONS.items():
        builtin = spec["builtin"]
        result.append(
            {
                "key": builtin["key"],
                "name": spec["name"],
                "template": template_key,
                "category": spec["category"],
                "description": spec["description"],
                "versions": [
                    {
                        "version": 1,
                        "name": builtin["version_name"],
                        "notes": builtin["notes"],
                        "is_default": True,
                        "config": normalize_strategy_config(
                            deepcopy(spec["config"]),
                            blank_strategy_config(),
                        ),
                        "parameter_space": deepcopy(spec["parameter_space"]),
                    }
                ],
            }
        )
    return result


def _template_payload(
    template_key: str,
    spec: dict[str, Any],
    indicator_map: dict[str, dict[str, Any]],
    contract: dict[str, Any],
    *,
    is_builtin: bool,
) -> dict[str, Any]:
    indicator_keys = list(spec["indicator_keys"])
    return {
        "template": template_key,
        "name": spec["name"],
        "category": spec["category"],
        "description": spec["description"],
        "is_builtin": is_builtin,
        "template_runtime": get_template_runtime(template_key),
        "indicator_keys": indicator_keys,
        "indicator_registry": [
            deepcopy(indicator_map[indicator_key])
            for indicator_key in indicator_keys
            if indicator_key in indicator_map
        ],
        "operators": deepcopy(contract["operators"]),
        "group_logics": deepcopy(contract["group_logics"]),
        "default_config": normalize_strategy_config(
            deepcopy(spec["config"]),
            contract["blank_config"],
        ),
        "default_parameter_space": deepcopy(spec["parameter_space"]),
    }
