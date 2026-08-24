from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.backtest.strategy_catalog import (
    normalize_custom_indicator_definition,
    normalize_custom_template_definition,
)
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import (
    IndicatorDefinition,
    StrategyDefinition,
    StrategyTemplateDefinition,
    StrategyVersion,
)


class StrategyDefinitionRepository:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def list_custom_indicators(self) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            rows = (
                session.query(IndicatorDefinition)
                .order_by(IndicatorDefinition.key.asc())
                .all()
            )
            return [self._indicator_payload(row) for row in rows]

    def list_custom_templates(self) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            rows = (
                session.query(StrategyTemplateDefinition)
                .order_by(StrategyTemplateDefinition.key.asc())
                .all()
            )
            return [self._template_payload(row) for row in rows]

    def list_strategy_definitions(self) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            rows = (
                session.query(StrategyDefinition)
                .order_by(StrategyDefinition.category.asc(), StrategyDefinition.name.asc())
                .all()
            )
            return [self._strategy_definition_payload(row) for row in rows]

    def list_strategy_versions(self, strategy_key: str | None = None) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            query = session.query(StrategyVersion)
            if strategy_key is not None:
                query = query.filter(StrategyVersion.strategy_key == strategy_key)
                query = query.order_by(
                    StrategyVersion.is_default.desc(),
                    StrategyVersion.version.desc(),
                )
            else:
                query = query.order_by(StrategyVersion.version.desc())
            return [self._strategy_version_payload(row) for row in query.all()]

    def create_indicator(
        self,
        *,
        key: str,
        name: str,
        engine_key: str,
        description: str | None,
        params: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        payload = normalize_custom_indicator_definition(
            key=key,
            name=name,
            engine_key=engine_key,
            description=description,
            params=params,
        )
        with self.database_runtime.session_scope() as session:
            existing = session.query(IndicatorDefinition).filter_by(key=payload["key"]).first()
            if existing:
                raise ValueError(f"指标已存在: {payload['key']}")
            row = IndicatorDefinition(
                key=payload["key"],
                name=payload["name"],
                engine=payload["engine"],
                description=payload["description"],
                outputs=deepcopy(payload["outputs"]),
                params=deepcopy(payload["params"]),
                is_builtin=False,
            )
            session.add(row)
            session.flush()
            return self._indicator_payload(row)

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
        custom_indicators = self.list_custom_indicators()
        payload = normalize_custom_template_definition(
            key=key,
            name=name,
            category=category,
            description=description,
            indicator_keys=indicator_keys,
            default_config=default_config,
            default_parameter_space=default_parameter_space,
            custom_indicators=custom_indicators,
        )
        with self.database_runtime.session_scope() as session:
            existing = session.query(StrategyTemplateDefinition).filter_by(key=payload["key"]).first()
            if existing:
                raise ValueError(f"模板已存在: {payload['key']}")
            row = StrategyTemplateDefinition(
                key=payload["key"],
                name=payload["name"],
                category=payload["category"],
                description=payload["description"],
                indicator_keys=deepcopy(payload["indicator_keys"]),
                default_config=deepcopy(payload["default_config"]),
                default_parameter_space=deepcopy(payload["default_parameter_space"]),
                is_builtin=False,
            )
            session.add(row)
            session.flush()
        return payload

    def create_strategy_version(
        self,
        *,
        key: str,
        definition_name: str,
        template: str,
        category: str,
        description: str | None,
        version_name: str,
        config: dict[str, Any],
        parameter_space: dict[str, list[Any]],
        notes: str | None,
        make_default: bool,
        base_version: int,
    ) -> dict[str, Any]:
        with self.database_runtime.session_scope() as session:
            definition = session.query(StrategyDefinition).filter_by(key=key).first()
            if not definition:
                definition = StrategyDefinition(
                    key=key,
                    name=definition_name,
                    template=template,
                    category=category,
                    description=description,
                    is_active=True,
                )
                session.add(definition)
                session.flush()
            else:
                definition.name = definition_name
                definition.template = template
                definition.category = category
                definition.description = description

            current_max = (
                session.query(StrategyVersion.version)
                .filter_by(strategy_key=key)
                .order_by(StrategyVersion.version.desc())
                .first()
            )
            next_version = max(current_max[0] if current_max else 0, base_version) + 1

            if make_default:
                session.query(StrategyVersion).filter_by(strategy_key=key).update(
                    {"is_default": False}
                )

            strategy_version = StrategyVersion(
                strategy_key=key,
                version=next_version,
                name=version_name,
                config=deepcopy(config),
                parameter_space=deepcopy(parameter_space),
                notes=notes,
                is_default=make_default or (current_max is None and base_version == 0),
            )
            session.add(strategy_version)
            session.flush()

            return {
                "definition": self._strategy_definition_payload(definition),
                "version": self._strategy_version_payload(strategy_version),
            }

    @staticmethod
    def _indicator_payload(row: IndicatorDefinition) -> dict[str, Any]:
        return {
            "key": row.key,
            "engine": row.engine,
            "name": row.name,
            "description": row.description,
            "outputs": deepcopy(row.outputs or []),
            "params": deepcopy(row.params or []),
            "is_builtin": False,
        }

    @staticmethod
    def _template_payload(row: StrategyTemplateDefinition) -> dict[str, Any]:
        return {
            "key": row.key,
            "name": row.name,
            "category": row.category,
            "description": row.description,
            "indicator_keys": deepcopy(row.indicator_keys or []),
            "default_config": deepcopy(row.default_config or {}),
            "default_parameter_space": deepcopy(row.default_parameter_space or {}),
            "is_builtin": False,
        }

    @staticmethod
    def _strategy_definition_payload(row: StrategyDefinition) -> dict[str, Any]:
        return {
            "key": row.key,
            "name": row.name,
            "template": row.template,
            "category": row.category,
            "description": row.description,
            "is_active": row.is_active,
        }

    @staticmethod
    def _strategy_version_payload(row: StrategyVersion) -> dict[str, Any]:
        return {
            "id": row.id,
            "strategy_key": row.strategy_key,
            "version": row.version,
            "name": row.name,
            "config": deepcopy(row.config or {}),
            "parameter_space": deepcopy(row.parameter_space or {}),
            "notes": row.notes,
            "is_default": row.is_default,
        }
