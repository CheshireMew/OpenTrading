from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FactorDefinition:
    factor_id: str
    name: str
    category: str
    source: str
    unit: str | None = None
    feature_mode: str = "level"
    description: str | None = None


DATASET_SCHEMA_VERSION = 1
SUPPORTED_TIMEFRAMES = ("1h", "4h", "1d")
SUPPORTED_CATEGORIES = ("Macro", "Onchain", "Sentiment", "Tech", "Derived")
DEFAULT_FORWARD_HORIZONS = (1, 3, 5, 10)
DEFAULT_CLEANING = {
    "winsorize_zscore": 4.0,
    "bucket_count": 5,
    "rolling_ic_window": 30,
    "min_sample_size": 60,
}
LEVEL_FACTOR_IDS = {"US10Y", "HY_SPREAD", "FED_RATE", "FEAR_GREED", "BTC_DRAWDOWN"}
DERIVED_FACTORS: tuple[FactorDefinition, ...] = (
    FactorDefinition("DERIVED_CLOSE_RETURN_1", "Price Return (1 Bar)", "Derived", "derived", "%", "level", "最近 1 根 K 线的价格涨跌幅。"),
    FactorDefinition("DERIVED_CLOSE_RETURN_5", "Price Return (5 Bars)", "Derived", "derived", "%", "level", "最近 5 根 K 线的累计涨跌幅。"),
    FactorDefinition("DERIVED_VOLUME_CHANGE_1", "Volume Change (1 Bar)", "Derived", "derived", "%", "level", "最近 1 根 K 线成交量变化率。"),
    FactorDefinition("DERIVED_REALIZED_VOL_20", "Realized Volatility (20 Bars)", "Derived", "derived", "%", "level", "最近 20 根 K 线的已实现波动率。"),
    FactorDefinition("DERIVED_RANGE_PCT", "Intrabar Range", "Derived", "derived", "%", "level", "单根 K 线振幅占收盘价比例。"),
    FactorDefinition("DERIVED_MA_GAP_20", "Price vs MA20 Gap", "Derived", "derived", "%", "level", "价格相对 20 均线的偏离比例。"),
)


def factor_from_meta(meta: Any) -> FactorDefinition:
    indicator_id = meta["id"]
    mode = "level" if indicator_id in LEVEL_FACTOR_IDS else "pct_change"
    return FactorDefinition(
        factor_id=indicator_id,
        name=meta["name"],
        category=meta["category"],
        source="indicator",
        unit=meta["unit"],
        feature_mode=mode,
        description=meta.get("description"),
    )


def serialize_factor(definition: FactorDefinition) -> dict[str, Any]:
    return {
        "factor_id": definition.factor_id,
        "name": definition.name,
        "category": definition.category,
        "source": definition.source,
        "unit": definition.unit,
        "feature_mode": definition.feature_mode,
        "description": definition.description,
    }
