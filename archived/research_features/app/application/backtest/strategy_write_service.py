from __future__ import annotations

from typing import Any

from app.application.backtest.ports import StrategyDefinitionStore
from app.contracts.backtest import StrategyVersionRecord
from app.domain.backtest.scripted_templates import template_supports_version_editing
from app.domain.backtest.strategy_catalog import (
    get_builtin_strategy_definitions,
    get_template_spec,
    get_template_runtime_contract,
)
from app.domain.backtest.strategy_support import (
    normalize_strategy_version_config_model,
    normalize_strategy_version_payload,
)


class StrategyWriteService:
    def __init__(self, *, definition_store: StrategyDefinitionStore) -> None:
        self.definition_store = definition_store

    def create_indicator(
        self,
        *,
        key: str,
        name: str,
        engine_key: str,
        description: str | None,
        params: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        return self.definition_store.create_indicator(
            key=key,
            name=name,
            engine_key=engine_key,
            description=description,
            params=params,
        )

    def create_template(
        self,
        *,
        key: str,
        name: str,
        category: str,
        description: str | None,
        indicator_keys: list[str],
        default_config: dict[str, Any],
        default_parameter_space: dict[str, list[Any]] | None,
    ) -> dict[str, Any]:
        template = self.definition_store.create_template(
            key=key,
            name=name,
            category=category,
            description=description,
            indicator_keys=indicator_keys,
            default_config=default_config,
            default_parameter_space=default_parameter_space,
        )
        return self._template_spec(template["key"])

    def create_strategy_version(
        self,
        *,
        key: str,
        name: str,
        template: str,
        category: str,
        description: str | None,
        config: dict[str, Any],
        parameter_space: dict[str, list[Any]] | None,
        notes: str | None,
        make_default: bool,
    ) -> StrategyVersionRecord:
        builtin_definition = self._get_builtin_definition(key)
        resolved_template = builtin_definition["template"] if builtin_definition else template
        resolved_name = builtin_definition["name"] if builtin_definition else name
        resolved_category = builtin_definition["category"] if builtin_definition else category
        resolved_description = builtin_definition.get("description") if builtin_definition else description

        runtime_contract = get_template_runtime_contract(resolved_template)
        if not template_supports_version_editing(runtime_contract):
            raise ValueError("该内置脚本策略当前只提供固定版本，不支持复制编辑")

        normalized_config, normalized_parameter_space = normalize_strategy_version_payload(
            resolved_template,
            config,
            parameter_space,
            template_spec=self._template_spec(resolved_template),
        )
        stored = self.definition_store.create_strategy_version(
            key=key,
            definition_name=resolved_name,
            template=resolved_template,
            category=resolved_category,
            description=resolved_description,
            version_name=name,
            config=normalize_strategy_version_config_model(
                resolved_template,
                normalized_config,
                template_spec=self._template_spec(resolved_template),
            ).model_dump(),
            parameter_space=normalized_parameter_space,
            notes=notes,
            make_default=make_default,
            base_version=1 if builtin_definition else 0,
        )
        definition = stored["definition"]
        version = stored["version"]
        return StrategyVersionRecord(
            strategy_key=definition["key"],
            strategy_name=definition["name"],
            version=version["version"],
            template=definition["template"],
            config=normalized_config,
            parameter_space=normalized_parameter_space,
            description=definition["description"],
            notes=version["notes"],
            version_name=version["name"],
            id=version["id"],
            is_default=version["is_default"],
        )

    def _get_builtin_definition(self, strategy_key: str) -> dict[str, Any] | None:
        return next(
            (
                definition
                for definition in get_builtin_strategy_definitions()
                if definition["key"] == strategy_key
            ),
            None,
        )

    def _template_spec(self, template: str) -> dict[str, Any]:
        custom_indicators = self.definition_store.list_custom_indicators()
        return get_template_spec(
            template,
            custom_indicators=custom_indicators,
            custom_templates=self.definition_store.list_custom_templates(),
        )
