from __future__ import annotations

from app.contracts.strategy import StrategyPartialExitResponse, StrategyTradePlanConfigResponse
from app.domain.backtest.freqtrade_exit_codegen import render_threshold_custom_exit
from app.domain.backtest.strategy_config_normalizer import normalize_strategy_identifier


class FreqtradeRiskCodegen:
    def build_trade_plan_block(self, trade_plan: StrategyTradePlanConfigResponse) -> str:
        atr_indicator = str(trade_plan.atr_indicator or "").strip()
        support_indicator = str(trade_plan.support_indicator or "").strip()
        resistance_indicator = str(trade_plan.resistance_indicator or "").strip()
        if not atr_indicator or not support_indicator or not resistance_indicator:
            raise ValueError("trade_plan 已启用，但缺少 ATR / 支撑 / 阻力指标")
        normalize_strategy_identifier(atr_indicator, "ATR 指标标识")
        normalize_strategy_identifier(support_indicator, "支撑指标标识")
        normalize_strategy_identifier(resistance_indicator, "阻力指标标识")
        stop_multiplier = float(trade_plan.stop_multiplier or 1.0)
        min_stop_pct = float(trade_plan.min_stop_pct or 0.01)
        reward_multiplier = float(trade_plan.reward_multiplier or 2.0)
        return f"""
    def _resolve_trade_plan(self, pair, trade):
        cached_plan = trade.get_custom_data("trade_plan")
        if cached_plan:
            return cached_plan
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None
        open_time = pd.Timestamp(trade.open_date_utc)
        entry_frame = dataframe.loc[dataframe["date"] <= open_time]
        if entry_frame.empty:
            return None
        entry_candle = entry_frame.iloc[-1]
        entry_price = float(trade.open_rate)
        atr_value = float(entry_candle.get("{atr_indicator}__value") or 0.0)
        stop_distance = max(atr_value * {stop_multiplier}, entry_price * {min_stop_pct})
        if trade.is_short:
            structure = float(entry_candle.get("{resistance_indicator}__value") or (entry_price + stop_distance))
            stop_price = max(entry_price + stop_distance, structure)
            target_price = entry_price - abs(entry_price - stop_price) * {reward_multiplier}
        else:
            structure = float(entry_candle.get("{support_indicator}__value") or (entry_price - stop_distance))
            stop_price = min(entry_price - stop_distance, structure)
            target_price = entry_price + abs(entry_price - stop_price) * {reward_multiplier}
        resolved_plan = {{"target": float(target_price), "stop": float(stop_price)}}
        if getattr(trade, "id", None) is not None:
            trade.set_custom_data("trade_plan", resolved_plan)
        return resolved_plan
{render_threshold_custom_exit(
    plan_var_name="trade_plan",
    resolve_plan_expression="self._resolve_trade_plan(pair, trade)",
    stop_reason="trade_plan_stop",
    target_reason="trade_plan_target",
)}"""

    @staticmethod
    def build_partial_exit_block(partial_exits: list[StrategyPartialExitResponse]) -> str:
        if not partial_exits:
            return ""
        steps = [
            {"profit": float(item.profit), "size_pct": float(item.size_pct)}
            for item in sorted(partial_exits, key=lambda item: float(item.profit))
            if float(item.size_pct) > 0
        ]
        if not steps:
            return ""
        return f"""
    def adjust_trade_position(self, trade, current_time, current_rate, current_profit, min_stake, max_stake, current_entry_rate, current_exit_rate, current_entry_profit, current_exit_profit, **kwargs):
        partial_steps = {repr(steps)}
        if trade.nr_of_successful_exits >= len(partial_steps):
            return None
        step = partial_steps[trade.nr_of_successful_exits]
        if current_profit < step["profit"]:
            return None
        reduction = trade.stake_amount * (step["size_pct"] / 100.0)
        if min_stake and reduction < min_stake:
            return None
        return -reduction, f"partial_{{trade.nr_of_successful_exits + 1}}"
"""
