from __future__ import annotations


def render_threshold_custom_exit(
    *,
    plan_var_name: str,
    resolve_plan_expression: str,
    stop_reason: str,
    target_reason: str,
) -> str:
    return f"""
    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None
        now = pd.Timestamp(current_time)
        current_frame = dataframe.loc[dataframe["date"] <= now]
        if current_frame.empty:
            return None
        current_candle = current_frame.iloc[-1]
        {plan_var_name} = {resolve_plan_expression}
        if not {plan_var_name}:
            return None
        current_high = float(current_candle["high"])
        current_low = float(current_candle["low"])
        if trade.is_short:
            if current_high >= float({plan_var_name}["stop"]):
                return "{stop_reason}"
            if current_low <= float({plan_var_name}["target"]):
                return "{target_reason}"
            return None
        if current_low <= float({plan_var_name}["stop"]):
            return "{stop_reason}"
        if current_high >= float({plan_var_name}["target"]):
            return "{target_reason}"
        return None
"""
