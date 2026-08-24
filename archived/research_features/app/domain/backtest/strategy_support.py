from __future__ import annotations

from typing import Any

from app.contracts.backtest import StrategyVersionRecord
from app.contracts.strategy import StrategyTemplateConfigResponse
from app.domain.backtest.strategy_catalog import get_template_spec
from app.domain.backtest.strategy_config_normalizer import (
    normalize_strategy_config_model,
    normalize_strategy_payload,
    strategy_runtime_profile,
)


def normalize_strategy_version_payload(
    template: str,
    config: dict[str, Any],
    parameter_space: dict[str, list[Any]] | None,
    *,
    template_spec: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    return normalize_strategy_payload(
        template_spec=template_spec or get_template_spec(template),
        config=dict(config or {}),
        parameter_space=dict(parameter_space or {}),
    )


def normalize_strategy_version_config_model(
    template: str,
    config: dict[str, Any] | StrategyTemplateConfigResponse,
    *,
    template_spec: dict[str, Any] | None = None,
) -> StrategyTemplateConfigResponse:
    if isinstance(config, StrategyTemplateConfigResponse):
        return config
    return normalize_strategy_config_model(
        dict(config or {}),
        (template_spec or get_template_spec(template))["default_config"],
    )


def blank_strategy_version_config_model() -> StrategyTemplateConfigResponse:
    from app.domain.backtest.strategy_config_normalizer import blank_strategy_config

    return StrategyTemplateConfigResponse.model_validate(blank_strategy_config())


def build_strategy_version_response_payload(
    record: StrategyVersionRecord,
    *,
    template_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record_config = dict(record.config or {})
    normalized_config, normalized_parameter_space = normalize_strategy_version_payload(
        record.template,
        record_config,
        record.parameter_space,
        template_spec=template_spec,
    )
    return {
        "id": record.id,
        "version": record.version,
        "name": record.version_name or record.strategy_name,
        "notes": record.notes,
        "is_default": record.is_default,
        "config": normalized_config,
        "parameter_space": normalized_parameter_space,
        "runtime": strategy_runtime_profile(normalized_config),
    }
