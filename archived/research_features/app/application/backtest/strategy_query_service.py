from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.application.backtest.ports import StrategyDefinitionStore
from app.contracts.backtest import StrategyVersionRecord
from app.contracts.backtest_defaults import backtest_run_defaults
from app.domain.backtest.strategy_catalog import (
    get_builtin_strategy_definitions,
    get_indicator_catalog,
    get_indicator_engine_catalog,
    get_template_catalog,
    get_template_runtime_contract,
    get_template_spec,
)
from app.domain.backtest.strategy_editor_contract import editor_contract
from app.domain.backtest.strategy_support import (
    build_strategy_version_response_payload,
    normalize_strategy_version_config_model,
    normalize_strategy_version_payload,
)


class StrategyQueryService:
    def __init__(self, *, definition_store: StrategyDefinitionStore) -> None:
        self.definition_store = definition_store

    def get_editor_contract(self) -> dict[str, Any]:
        contract = editor_contract()
        contract["run_defaults"] = backtest_run_defaults()
        return contract

    def list_templates(self) -> list[dict[str, Any]]:
        return self._template_catalog()

    def list_indicators(self) -> list[dict[str, Any]]:
        return get_indicator_catalog(self.definition_store.list_custom_indicators())

    def list_indicator_engines(self) -> list[dict[str, Any]]:
        return get_indicator_engine_catalog()

    def list_strategies(self) -> list[dict[str, Any]]:
        definitions = self.definition_store.list_strategy_definitions()
        version_rows = self.definition_store.list_strategy_versions()

        versions_by_key: dict[str, list[dict[str, Any]]] = {}
        for version_row in version_rows:
            versions_by_key.setdefault(version_row["strategy_key"], []).append(
                version_row
            )

        result: list[dict[str, Any]] = []
        builtin_by_key = {
            item["key"]: deepcopy(item) for item in get_builtin_strategy_definitions()
        }

        for strategy_key, builtin in builtin_by_key.items():
            db_versions = [
                row
                for row in versions_by_key.get(strategy_key, [])
                if row["version"] != 1
            ]
            has_custom_default = any(row["is_default"] for row in db_versions)
            builtin_versions = []
            for version_payload in builtin["versions"]:
                builtin_versions.append(
                    build_strategy_version_response_payload(
                        StrategyVersionRecord(
                            strategy_key=strategy_key,
                            strategy_name=builtin["name"],
                            version=version_payload["version"],
                            template=builtin["template"],
                            config=normalize_strategy_version_config_model(
                                builtin["template"],
                                version_payload["config"] or {},
                                template_spec=self._template_spec(builtin["template"]),
                            ).model_dump(),
                            parameter_space=version_payload.get("parameter_space")
                            or {},
                            notes=version_payload.get("notes"),
                            version_name=version_payload["name"],
                            id=None,
                            is_default=version_payload.get("is_default", False)
                            and not has_custom_default,
                        ),
                        template_spec=self._template_spec(builtin["template"]),
                    )
                )

            result.append(
                {
                    "key": strategy_key,
                    "name": builtin["name"],
                    "template": builtin["template"],
                    "category": builtin["category"],
                    "description": builtin.get("description"),
                    "is_active": True,
                    "template_runtime": get_template_runtime_contract(
                        builtin["template"]
                    ),
                    "versions": [
                        *self._build_db_versions(builtin["template"], db_versions),
                        *builtin_versions,
                    ],
                }
            )

        for definition in definitions:
            if definition["key"] in builtin_by_key:
                continue
            result.append(
                {
                    "key": definition["key"],
                    "name": definition["name"],
                    "template": definition["template"],
                    "category": definition["category"],
                    "description": definition["description"],
                    "is_active": definition["is_active"],
                    "template_runtime": get_template_runtime_contract(
                        definition["template"]
                    ),
                    "versions": self._build_db_versions(
                        definition["template"],
                        versions_by_key.get(definition["key"], []),
                    ),
                }
            )

        return sorted(
            result,
            key=lambda item: (item["category"], item["name"].lower()),
        )

    def get_strategy_version(
        self, strategy_key: str, version: int | None = None
    ) -> StrategyVersionRecord:
        builtin_definition = self._get_builtin_definition(strategy_key)
        definition = next(
            (
                row
                for row in self.definition_store.list_strategy_definitions()
                if row["key"] == strategy_key
            ),
            None,
        )
        db_versions = self.definition_store.list_strategy_versions(strategy_key)

        if builtin_definition:
            filtered_versions = [row for row in db_versions if row["version"] != 1]
            selected = None
            if version is None:
                selected = next(
                    (row for row in filtered_versions if row["is_default"]), None
                )
                if selected is None:
                    return self._build_builtin_version_record(builtin_definition)
            elif version == 1:
                return self._build_builtin_version_record(builtin_definition)
            else:
                selected = next(
                    (row for row in filtered_versions if row["version"] == version),
                    None,
                )

            if selected is None:
                raise ValueError(
                    f"策略不存在: {strategy_key} v{version if version is not None else 'default'}"
                )
            return self._build_strategy_version_record(
                definition_name=builtin_definition["name"],
                description=builtin_definition.get("description"),
                template=builtin_definition["template"],
                strategy_key=strategy_key,
                strategy_version=selected,
            )

        if not definition:
            raise ValueError(
                f"策略不存在: {strategy_key} v{version if version is not None else 'default'}"
            )

        if version is None:
            selected = db_versions[0] if db_versions else None
        else:
            selected = next(
                (row for row in db_versions if row["version"] == version), None
            )
        if selected is None:
            raise ValueError(
                f"策略不存在: {strategy_key} v{version if version is not None else 'default'}"
            )
        return self._build_strategy_version_record(
            definition_name=definition["name"],
            description=definition["description"],
            template=definition["template"],
            strategy_key=strategy_key,
            strategy_version=selected,
        )

    def _build_db_versions(
        self, template: str, versions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            build_strategy_version_response_payload(
                StrategyVersionRecord(
                    strategy_key=version["strategy_key"],
                    strategy_name=version["name"],
                    version=version["version"],
                    template=template,
                    config=normalize_strategy_version_config_model(
                        template,
                        version["config"] or {},
                    ).model_dump(),
                    parameter_space=version["parameter_space"] or {},
                    notes=version["notes"],
                    version_name=version["name"],
                    id=version["id"],
                    is_default=version["is_default"],
                ),
                template_spec=self._template_spec(template),
            )
            for version in versions
        ]

    def _build_builtin_version_record(
        self, definition: dict[str, Any]
    ) -> StrategyVersionRecord:
        version_payload = definition["versions"][0]
        (
            normalized_config,
            normalized_parameter_space,
        ) = normalize_strategy_version_payload(
            definition["template"],
            version_payload["config"] or {},
            version_payload.get("parameter_space") or {},
            template_spec=self._template_spec(definition["template"]),
        )
        return StrategyVersionRecord(
            strategy_key=definition["key"],
            strategy_name=definition["name"],
            version=version_payload["version"],
            template=definition["template"],
            config=normalize_strategy_version_config_model(
                definition["template"],
                normalized_config,
                template_spec=self._template_spec(definition["template"]),
            ).model_dump(),
            parameter_space=normalized_parameter_space,
            description=definition.get("description"),
            notes=version_payload.get("notes"),
            version_name=version_payload["name"],
            id=None,
            is_default=True,
        )

    def _build_strategy_version_record(
        self,
        *,
        definition_name: str,
        description: str | None,
        template: str,
        strategy_key: str,
        strategy_version: dict[str, Any],
    ) -> StrategyVersionRecord:
        (
            normalized_config,
            normalized_parameter_space,
        ) = normalize_strategy_version_payload(
            template,
            strategy_version["config"] or {},
            strategy_version["parameter_space"] or {},
            template_spec=self._template_spec(template),
        )
        return StrategyVersionRecord(
            strategy_key=strategy_key,
            strategy_name=definition_name,
            version=strategy_version["version"],
            template=template,
            config=normalize_strategy_version_config_model(
                template,
                normalized_config,
                template_spec=self._template_spec(template),
            ).model_dump(),
            parameter_space=normalized_parameter_space,
            description=description,
            notes=strategy_version["notes"],
            version_name=strategy_version["name"],
            id=strategy_version["id"],
            is_default=strategy_version["is_default"],
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

    def _template_catalog(self) -> list[dict[str, Any]]:
        custom_indicators = self.definition_store.list_custom_indicators()
        return get_template_catalog(
            custom_indicators=custom_indicators,
            custom_templates=self.definition_store.list_custom_templates(),
        )

    def _template_spec(self, template: str) -> dict[str, Any]:
        custom_indicators = self.definition_store.list_custom_indicators()
        return get_template_spec(
            template,
            custom_indicators=custom_indicators,
            custom_templates=self.definition_store.list_custom_templates(),
        )
