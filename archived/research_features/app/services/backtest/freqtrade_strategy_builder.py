from __future__ import annotations

from typing import Any

from app.contracts.strategy import StrategyIndicatorConfigResponse, StrategyTemplateConfigResponse
from app.domain.backtest.scripted_templates import (
    get_template_runtime,
    require_scripted_template,
    template_builder_kind,
)
from app.domain.backtest.freqtrade_strategy_runtime import (
    render_freqtrade_strategy_runtime,
    resolve_freqtrade_strategy_runtime,
)
from app.domain.backtest.indicator_engines import (
    indicator_engine_definition,
)
from app.domain.backtest.strategy_catalog import get_indicator_registry_map
from app.domain.backtest.strategy_config_normalizer import normalize_strategy_identifier
from app.services.backtest.freqtrade_risk_codegen import FreqtradeRiskCodegen
from app.services.backtest.freqtrade_rule_codegen import FreqtradeRuleCodegen
from app.services.backtest.strategy_parameter_space import candidate_strategy_configs
from app.services.backtest.strategy_runtime import StrategyRuntime


class FreqtradeStrategyBuilder:
    def __init__(self, strategy_class_name: str) -> None:
        self.strategy_class_name = strategy_class_name
        self.runtime = StrategyRuntime()
        self.rule_codegen = FreqtradeRuleCodegen()
        self.risk_codegen = FreqtradeRiskCodegen()

    def build_code(self, template: str, timeframe: str, config: dict[str, Any] | StrategyTemplateConfigResponse) -> str:
        runtime_contract = get_template_runtime(template)
        if template_builder_kind(runtime_contract) == "scripted":
            return require_scripted_template(template).build_strategy_code(
                strategy_class_name=self.strategy_class_name,
                timeframe=timeframe,
            )
        normalized_config = self.runtime.normalized_config(template, config)
        trade_settings = self.trade_settings(template, normalized_config)
        indicator_registry = get_indicator_registry_map()
        risk = normalized_config.risk
        trade_plan = risk.trade_plan
        uses_trade_plan = bool(trade_plan.enabled)
        can_short = normalized_config.execution.direction == "long_short"
        indicator_script = self._build_indicator_script(normalized_config, indicator_registry, timeframe)
        regime_priority = normalized_config.regime_priority or ["trend", "range"]
        branch_masks = self.rule_codegen.build_branch_masks(normalized_config, regime_priority)
        entry_assignments = self.rule_codegen.build_signal_assignments(
            normalized_config,
            regime_priority,
            branch_masks,
            signal_kind="entry",
            can_short=can_short,
        )
        exit_assignments = self.rule_codegen.build_exit_assignments(
            normalized_config,
            regime_priority,
            branch_masks,
            can_short=can_short,
            uses_trade_plan=uses_trade_plan,
        )
        roi_targets = {
            str(int(item.minutes)): float(item.profit)
            for item in sorted([item for item in risk.roi_targets if item.enabled], key=lambda item: int(item.minutes), reverse=True)
        }
        if uses_trade_plan:
            roi_targets = {"0": 99.0}
        partial_exits = [item for item in risk.partial_exits if item.enabled]
        partial_exit_block = self.risk_codegen.build_partial_exit_block(partial_exits)
        trade_plan_block = self.risk_codegen.build_trade_plan_block(trade_plan) if uses_trade_plan else ""
        warmup_bars = self.warmup_bars(template, normalized_config, timeframe)
        runtime_block = render_freqtrade_strategy_runtime(
            resolve_freqtrade_strategy_runtime(
                can_short=can_short,
                timeframe=timeframe,
                startup_candle_count=warmup_bars,
                risk=risk.model_dump(),
                roi_targets=roi_targets,
                order_types=trade_settings["order_types"],
                has_exit_signals=True,
                has_custom_exit=uses_trade_plan,
                position_adjustment_enable=bool(partial_exits),
            )
        )
        return f"""import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy


class {self.strategy_class_name}(IStrategy):
{runtime_block}

    def _resample_ohlcv(self, dataframe: DataFrame, timeframe: str) -> DataFrame:
        rule_map = {{"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}}
        if timeframe not in rule_map:
            raise ValueError(f"Unsupported timeframe: {{timeframe}}")
        indexed = dataframe[["date", "open", "high", "low", "close", "volume"]].copy().set_index("date")
        resampled = (
            indexed.resample(rule_map[timeframe], label="right", closed="right")
            .agg({{"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}})
            .dropna()
            .reset_index()
        )
        return resampled

    def _merge_indicator_frame(self, dataframe: DataFrame, informative: DataFrame, columns: list[str]) -> DataFrame:
        if not columns:
            return dataframe
        return pd.merge_asof(
            dataframe.sort_values("date"),
            informative[["date", *columns]].sort_values("date"),
            on="date",
            direction="backward",
        )

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
{indicator_script}
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = None
{entry_assignments}
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = None
{exit_assignments}
        return dataframe
{partial_exit_block}
{trade_plan_block}
"""

    def warmup_bars(self, template: str, config: dict[str, Any] | StrategyTemplateConfigResponse, timeframe: str) -> int:
        runtime_contract = get_template_runtime(template)
        if template_builder_kind(runtime_contract) == "scripted":
            payload = config.model_dump() if isinstance(config, StrategyTemplateConfigResponse) else config
            return require_scripted_template(template).warmup_bars(payload, timeframe)
        payload = config.model_dump() if isinstance(config, StrategyTemplateConfigResponse) else config
        return self.runtime.warmup_bars(template, payload, timeframe)

    def trade_settings(self, template: str, config: dict[str, Any] | StrategyTemplateConfigResponse) -> dict[str, Any]:
        runtime_contract = get_template_runtime(template)
        if template_builder_kind(runtime_contract) == "scripted":
            payload = config.model_dump() if isinstance(config, StrategyTemplateConfigResponse) else config
            return require_scripted_template(template).trade_settings(payload)
        normalized_config = config if isinstance(config, StrategyTemplateConfigResponse) else self.runtime.normalized_config(template, config)
        partial_exits = [item for item in normalized_config.risk.partial_exits if item.enabled]
        order_types = {
            "entry": "market",
            "exit": "market",
            "stoploss": "market",
            "stoploss_on_exchange": False,
        }
        uses_market_entry = order_types.get("entry") == "market"
        uses_market_exit = order_types.get("exit") == "market"
        return {
            "order_types": order_types,
            "position_adjustment_enable": bool(partial_exits),
            "entry_pricing": {
                "price_side": "other" if uses_market_entry else "same",
                "use_order_book": True,
                "order_book_top": 1,
                "price_last_balance": 0.0,
                "check_depth_of_market": {"enabled": False, "bids_to_ask_delta": 1},
            },
            "exit_pricing": {
                "price_side": "other" if uses_market_exit else "same",
                "use_order_book": True,
                "order_book_top": 1,
            },
        }

    def candidate_configs(self, base_config: dict[str, Any], parameter_space: dict[str, list[Any]], optimize_trials: int):
        yield from candidate_strategy_configs(base_config, parameter_space, optimize_trials)

    def _build_indicator_script(
        self,
        normalized_config: StrategyTemplateConfigResponse,
        indicator_registry: dict[str, dict[str, Any]],
        base_timeframe: str,
    ) -> str:
        indicators = normalized_config.indicators
        timeframes: dict[str, list[tuple[str, StrategyIndicatorConfigResponse, dict[str, Any]]]] = {}
        for indicator_id, indicator in indicators.items():
            indicator_timeframe = indicator.timeframe or "base"
            resolved_timeframe = base_timeframe if indicator_timeframe == "base" else indicator_timeframe
            indicator_spec = indicator_registry.get(indicator.type) or {}
            timeframes.setdefault(resolved_timeframe, []).append((indicator_id, indicator, indicator_spec))

        lines = ["        dataframe = dataframe.sort_values(\"date\").copy()"]
        frame_vars: dict[str, str] = {base_timeframe: "dataframe"}
        for timeframe in sorted([key for key in timeframes.keys() if key != base_timeframe], key=self._timeframe_sort_key):
            frame_var = f'frame_{timeframe.replace("m", "m").replace("h", "h").replace("d", "d")}'
            frame_vars[timeframe] = frame_var
            lines.append(f'        {frame_var} = self._resample_ohlcv(dataframe, "{timeframe}")')

        for timeframe, indicator_items in timeframes.items():
            frame_var = frame_vars[timeframe]
            for indicator_id, indicator, indicator_spec in indicator_items:
                normalize_strategy_identifier(indicator_id, "指标标识")
                engine = indicator_engine_definition(indicator.type, indicator_spec)
                lines.extend(
                    engine.render_code(
                        frame_var,
                        indicator_id,
                        indicator.params,
                    )
                )

        for timeframe in sorted([key for key in timeframes.keys() if key != base_timeframe], key=self._timeframe_sort_key):
            frame_var = frame_vars[timeframe]
            columns = [
                column
                for indicator_id, indicator, indicator_spec in timeframes[timeframe]
                for column in indicator_engine_definition(indicator.type, indicator_spec).output_columns(indicator_id)
            ]
            lines.append(f"        dataframe = self._merge_indicator_frame(dataframe, {frame_var}, {repr(columns)})")
        return "\n".join(lines)

    def _timeframe_sort_key(self, timeframe: str) -> int:
        from app.domain.market.timeframes import timeframe_to_minutes

        return timeframe_to_minutes(timeframe)
