from __future__ import annotations

import re

STRATEGY_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
PRICE_SOURCE_FIELDS = {"open", "high", "low", "close", "volume"}

RULE_OPERATORS: list[dict[str, str]] = [
    {"key": "gt", "label": "大于"},
    {"key": "gte", "label": "大于等于"},
    {"key": "lt", "label": "小于"},
    {"key": "lte", "label": "小于等于"},
]

GROUP_LOGICS: list[dict[str, str]] = [
    {"key": "and", "label": "全部满足"},
    {"key": "or", "label": "满足任一"},
]

TIMEFRAME_OPTIONS: list[dict[str, str]] = [
    {"key": "base", "label": "跟随运行周期"},
    {"key": "1m", "label": "1 分钟"},
    {"key": "5m", "label": "5 分钟"},
    {"key": "15m", "label": "15 分钟"},
    {"key": "1h", "label": "1 小时"},
    {"key": "4h", "label": "4 小时"},
    {"key": "1d", "label": "1 天"},
]

RUN_TIMEFRAME_KEYS: list[str] = [item["key"] for item in TIMEFRAME_OPTIONS if item["key"] != "base"]

MARKET_TYPE_OPTIONS: list[dict[str, str]] = [
    {"key": "spot", "label": "现货"},
    {"key": "futures", "label": "合约"},
]

DIRECTION_OPTIONS: list[dict[str, str]] = [
    {"key": "long_only", "label": "只做多"},
    {"key": "long_short", "label": "多空双向"},
]

STRATEGY_CONFIG_FIELDS = {
    "indicators",
    "execution",
    "regime_priority",
    "trend",
    "range",
    "risk",
}
