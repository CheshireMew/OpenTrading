from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from app.contracts.strategy import StrategyIndicatorConfigResponse, StrategyTemplateConfigResponse
from app.domain.backtest.indicator_engines import indicator_engine_definition
from app.domain.backtest.strategy_catalog import get_indicator_registry_map, get_template_spec
from app.domain.backtest.strategy_config_normalizer import (
    allowed_run_timeframes,
    explicit_indicator_timeframes,
    normalize_strategy_config_model,
    preferred_run_timeframe,
)
from app.domain.market.timeframes import timeframe_to_minutes
from app.services.backtest.strategy_frame_builder import (
    StrategySignalFrameBuilder,
    resolve_indicator_timeframe,
)
from utils.time_utils import to_utc_naive_datetime


@dataclass(slots=True)
class StrategySignalSnapshot:
    timestamp: datetime
    price: float
    active_regime: str | None
    long_entry_signal: bool
    long_exit_signal: bool
    short_entry_signal: bool
    short_exit_signal: bool
    indicators: dict[str, Any]


class StrategyRuntime:
    def __init__(self, frame_builder: StrategySignalFrameBuilder | None = None) -> None:
        self.frame_builder = frame_builder or StrategySignalFrameBuilder()

    def normalized_config(self, template: str, config: dict[str, Any] | StrategyTemplateConfigResponse) -> StrategyTemplateConfigResponse:
        if isinstance(config, StrategyTemplateConfigResponse):
            return config
        return normalize_strategy_config_model(
            config=dict(config or {}),
            default_config=get_template_spec(template)["default_config"],
        )

    def validate_timeframe_compatibility(self, template: str, config: dict[str, Any] | StrategyTemplateConfigResponse, base_timeframe: str) -> StrategyTemplateConfigResponse:
        normalized_config = self.normalized_config(template, config)
        config_payload = normalized_config.model_dump()
        if base_timeframe not in allowed_run_timeframes(config_payload):
            indicator_details = []
            for indicator_id, indicator in normalized_config.indicators.items():
                indicator_timeframe = resolve_indicator_timeframe(indicator, base_timeframe)
                label = str(indicator.label or indicator_id)
                indicator_details.append(f"{label}({indicator_timeframe})")
            joined = ", ".join(indicator_details) if indicator_details else ", ".join(explicit_indicator_timeframes(config_payload))
            raise ValueError(
                f"运行周期 {base_timeframe} 与策略指标周期不兼容。"
                f"当前策略包含更细周期或非整倍数周期指标: {joined}。"
                f"请把运行周期调到 {preferred_run_timeframe(config_payload)}，或改掉对应指标周期。"
            )
        return normalized_config

    def warmup_bars(self, template: str, config: dict[str, Any] | StrategyTemplateConfigResponse, base_timeframe: str) -> int:
        normalized_config = self.validate_timeframe_compatibility(template, config, base_timeframe)
        indicator_registry = get_indicator_registry_map()
        base_minutes = timeframe_to_minutes(base_timeframe)
        warmups = [5]
        for indicator in normalized_config.indicators.values():
            indicator_type = indicator.type
            indicator_spec = indicator_registry.get(indicator_type) or {}
            params = indicator.params
            indicator_timeframe = resolve_indicator_timeframe(indicator, base_timeframe)
            scale = max(timeframe_to_minutes(indicator_timeframe) // base_minutes, 1)
            warmups.append(indicator_engine_definition(indicator_type, indicator_spec).warmup(params) * scale)
        return max(warmups) + 5

    def build_signal_snapshots(
        self,
        template: str,
        config: dict[str, Any] | StrategyTemplateConfigResponse,
        candles: list[list[float]],
        timeframe: str,
        *,
        after_timestamp_ms: int | None = None,
    ) -> list[StrategySignalSnapshot]:
        frame = self.build_frame(template, config, candles, timeframe)
        if frame.empty:
            return []
        if after_timestamp_ms is not None:
            frame = frame[frame["timestamp"] > after_timestamp_ms]
        if frame.empty:
            return []
        indicators = self.normalized_config(template, config).indicators
        return [
            StrategySignalSnapshot(
                timestamp=to_utc_naive_datetime(row["date"]),
                price=float(row["close"]),
                active_regime=str(row["active_regime"]) if row.get("active_regime") else None,
                long_entry_signal=bool(row["long_entry_signal"]),
                long_exit_signal=bool(row["long_exit_signal"]),
                short_entry_signal=bool(row["short_entry_signal"]),
                short_exit_signal=bool(row["short_exit_signal"]),
                indicators=self._row_indicator_snapshot(row, indicators),
            )
            for _, row in frame.iterrows()
        ]

    def build_frame(
        self,
        template: str,
        config: dict[str, Any] | StrategyTemplateConfigResponse,
        candles: list[list[float]],
        timeframe: str,
    ) -> pd.DataFrame:
        normalized_config = self.validate_timeframe_compatibility(template, config, timeframe)
        return self.frame_builder.build_frame(template, normalized_config, candles, timeframe)

    def _row_indicator_snapshot(self, row: pd.Series, indicators: dict[str, StrategyIndicatorConfigResponse]) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for indicator_id, indicator in indicators.items():
            values: dict[str, Any] = {}
            prefix = f"{indicator_id}__"
            for key in row.index:
                if not str(key).startswith(prefix):
                    continue
                output_key = str(key)[len(prefix):]
                values[output_key] = self._coerce_scalar(row[key])
            snapshot[indicator_id] = {
                "label": indicator.label or indicator_id,
                "type": indicator.type,
                "timeframe": indicator.timeframe,
                "values": values,
            }
        return snapshot

    def _coerce_scalar(self, value: Any) -> Any:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if pd.isna(value):
            return None
        if isinstance(value, (pd.Timestamp, datetime)):
            return to_utc_naive_datetime(value).isoformat()
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                return value
        return value
