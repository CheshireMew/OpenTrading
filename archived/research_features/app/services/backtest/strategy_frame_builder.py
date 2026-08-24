from __future__ import annotations

from typing import Any

import pandas as pd

from app.contracts.strategy import StrategyIndicatorConfigResponse, StrategyTemplateConfigResponse
from app.domain.backtest.indicator_engines import indicator_engine_definition
from app.domain.backtest.scripted_templates import get_template_runtime, require_scripted_template, template_builder_kind
from app.domain.backtest.strategy_catalog import get_indicator_registry_map
from app.domain.backtest.strategy_rule_tree import strategy_branch
from app.domain.market.timeframes import timeframe_to_minutes
from app.services.backtest.strategy_rule_evaluator import StrategyRuleEvaluator


class StrategySignalFrameBuilder:
    def __init__(self, rule_evaluator: StrategyRuleEvaluator | None = None) -> None:
        self.rule_evaluator = rule_evaluator or StrategyRuleEvaluator()

    def build_frame(
        self,
        template: str,
        config: StrategyTemplateConfigResponse,
        candles: list[list[float]],
        timeframe: str,
    ) -> pd.DataFrame:
        runtime_contract = get_template_runtime(template)
        if template_builder_kind(runtime_contract) == "scripted":
            return require_scripted_template(template).build_signal_frame(candles, timeframe)
        frame = self.base_frame(candles)
        if frame.empty:
            return frame
        indicator_registry = get_indicator_registry_map()
        frame = self._merge_indicator_frames(frame, config, indicator_registry, timeframe)
        branch_masks = self.rule_evaluator.resolve_branch_masks(frame, config)
        frame["active_regime"] = pd.Series([None] * len(frame), index=frame.index, dtype=object)
        frame["long_entry_signal"] = pd.Series(False, index=frame.index, dtype=bool)
        frame["long_exit_signal"] = pd.Series(False, index=frame.index, dtype=bool)
        frame["short_entry_signal"] = pd.Series(False, index=frame.index, dtype=bool)
        frame["short_exit_signal"] = pd.Series(False, index=frame.index, dtype=bool)
        allow_short = config.execution.direction == "long_short"
        for branch_key in config.regime_priority or ["trend", "range"]:
            branch = strategy_branch(config, branch_key)
            mask = branch_masks.get(branch_key)
            if mask is None:
                continue
            frame.loc[mask, "active_regime"] = branch_key
            frame["long_entry_signal"] = frame["long_entry_signal"] | (mask & self.rule_evaluator.evaluate_signal_rule_tree(frame, branch.long_entry))
            frame["long_exit_signal"] = frame["long_exit_signal"] | (mask & self.rule_evaluator.evaluate_signal_rule_tree(frame, branch.long_exit))
            if allow_short:
                frame["short_entry_signal"] = frame["short_entry_signal"] | (mask & self.rule_evaluator.evaluate_signal_rule_tree(frame, branch.short_entry))
                frame["short_exit_signal"] = frame["short_exit_signal"] | (mask & self.rule_evaluator.evaluate_signal_rule_tree(frame, branch.short_exit))
        return frame

    def base_frame(self, candles: list[list[float]]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame(columns=["timestamp", "date", "open", "high", "low", "close", "volume"])
        frame = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        frame["date"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        frame = frame.sort_values("date").reset_index(drop=True)
        return frame

    def _merge_indicator_frames(
        self,
        frame: pd.DataFrame,
        config: StrategyTemplateConfigResponse,
        indicator_registry: dict[str, dict[str, Any]],
        base_timeframe: str,
    ) -> pd.DataFrame:
        timeframe_frames: dict[str, pd.DataFrame] = {base_timeframe: frame.copy()}
        for indicator in config.indicators.values():
            indicator_timeframe = resolve_indicator_timeframe(indicator, base_timeframe)
            if indicator_timeframe not in timeframe_frames:
                timeframe_frames[indicator_timeframe] = self._resample_frame(frame, indicator_timeframe, base_timeframe)
        for indicator_id, indicator in config.indicators.items():
            indicator_timeframe = resolve_indicator_timeframe(indicator, base_timeframe)
            indicator_spec = indicator_registry.get(indicator.type) or {}
            indicator_engine_definition(indicator.type, indicator_spec).apply(
                timeframe_frames[indicator_timeframe],
                indicator_id,
                indicator.params,
            )
        merged = frame.copy()
        for indicator_id, indicator in config.indicators.items():
            indicator_timeframe = resolve_indicator_timeframe(indicator, base_timeframe)
            source_frame = timeframe_frames[indicator_timeframe]
            output_columns = [column for column in source_frame.columns if column.startswith(f"{indicator_id}__")]
            if not output_columns:
                continue
            if indicator_timeframe == base_timeframe:
                for column in output_columns:
                    merged[column] = source_frame[column]
                continue
            merge_frame = source_frame[["date", *output_columns]].sort_values("date")
            merged = pd.merge_asof(
                merged.sort_values("date"),
                merge_frame,
                on="date",
                direction="backward",
            )
        return merged

    def _resample_frame(self, frame: pd.DataFrame, target_timeframe: str, base_timeframe: str) -> pd.DataFrame:
        base_minutes = timeframe_to_minutes(base_timeframe)
        target_minutes = timeframe_to_minutes(target_timeframe)
        if target_minutes < base_minutes or target_minutes % base_minutes != 0:
            raise ValueError(f"指标周期必须大于等于运行周期且为整数倍: base={base_timeframe}, indicator={target_timeframe}")
        if target_timeframe == base_timeframe:
            return frame.copy()
        rule = pandas_timeframe_rule(target_timeframe)
        indexed = frame[["date", "open", "high", "low", "close", "volume"]].set_index("date")
        resampled = (
            indexed.resample(rule, label="right", closed="right")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
            .reset_index()
        )
        resampled["timestamp"] = resampled["date"].astype("int64").floordiv(1_000_000)
        return resampled[["timestamp", "date", "open", "high", "low", "close", "volume"]]


def pandas_timeframe_rule(timeframe: str) -> str:
    mapping = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1D",
    }
    if timeframe not in mapping:
        raise ValueError(f"不支持的重采样周期: {timeframe}")
    return mapping[timeframe]


def resolve_indicator_timeframe(indicator: StrategyIndicatorConfigResponse, base_timeframe: str) -> str:
    configured = str(indicator.timeframe or "base")
    return base_timeframe if configured == "base" else configured
