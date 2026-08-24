from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

import pandas as pd

from app.domain.backtest.scripted_templates import btc_regime_pulse_supertrend


class ScriptedTemplate(Protocol):
    TEMPLATE_KEY: str
    RUNTIME_CONTRACT: dict[str, Any]

    def build_signal_frame(self, candles: list[list[float]], timeframe: str) -> pd.DataFrame:
        ...

    def build_strategy_code(self, *, strategy_class_name: str, timeframe: str) -> str:
        ...

    def warmup_bars(self, config: dict[str, Any], timeframe: str) -> int:
        ...

    def trade_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        ...


RULES_TEMPLATE_RUNTIME: dict[str, Any] = {
    "builder_kind": "rules",
    "capabilities": {
        "paper": True,
        "version_editing": True,
    },
}

SCRIPTED_TEMPLATES: dict[str, ScriptedTemplate] = {
    btc_regime_pulse_supertrend.TEMPLATE_KEY: btc_regime_pulse_supertrend,
}


def get_template_runtime(template: str) -> dict[str, Any]:
    scripted_template = SCRIPTED_TEMPLATES.get(template)
    if scripted_template is not None:
        return deepcopy(scripted_template.RUNTIME_CONTRACT)
    return deepcopy(RULES_TEMPLATE_RUNTIME)


def template_builder_kind(runtime: dict[str, Any]) -> str:
    return str(runtime.get("builder_kind") or "rules")


def template_supports_paper(runtime: dict[str, Any]) -> bool:
    return bool((runtime.get("capabilities") or {}).get("paper", True))


def template_supports_version_editing(runtime: dict[str, Any]) -> bool:
    return bool((runtime.get("capabilities") or {}).get("version_editing", True))


def is_scripted_template(template: str) -> bool:
    return template in SCRIPTED_TEMPLATES


def require_scripted_template(template: str) -> ScriptedTemplate:
    scripted_template = SCRIPTED_TEMPLATES.get(template)
    if scripted_template is None:
        raise ValueError(f"不支持的脚本化策略模板: {template}")
    return scripted_template
