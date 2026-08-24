from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FreqtradeStrategyRuntimeConfig:
    can_short: bool
    timeframe: str
    startup_candle_count: int
    use_exit_signal: bool
    exit_profit_only: bool
    ignore_roi_if_entry_signal: bool
    minimal_roi: dict[str, float]
    stoploss: float
    trailing_stop: bool
    trailing_stop_positive: float
    trailing_stop_positive_offset: float
    trailing_only_offset_is_reached: bool
    position_adjustment_enable: bool
    order_types: dict[str, Any]


def resolve_freqtrade_strategy_runtime(
    *,
    can_short: bool,
    timeframe: str,
    startup_candle_count: int,
    risk: dict[str, Any] | None,
    roi_targets: dict[str, float] | None,
    order_types: dict[str, Any],
    has_exit_signals: bool,
    has_custom_exit: bool,
    position_adjustment_enable: bool,
) -> FreqtradeStrategyRuntimeConfig:
    risk_payload = dict(risk or {})
    trailing = dict(risk_payload.get("trailing") or {})
    uses_exit_path = bool(has_exit_signals or has_custom_exit)
    return FreqtradeStrategyRuntimeConfig(
        can_short=bool(can_short),
        timeframe=timeframe,
        startup_candle_count=int(startup_candle_count),
        use_exit_signal=uses_exit_path,
        exit_profit_only=False,
        ignore_roi_if_entry_signal=False,
        minimal_roi={str(key): float(value) for key, value in (roi_targets or {}).items()},
        stoploss=float(risk_payload.get("stoploss", -0.1)),
        trailing_stop=bool(trailing.get("enabled", False)),
        trailing_stop_positive=float(trailing.get("positive", 0.0)),
        trailing_stop_positive_offset=float(trailing.get("offset", 0.0)),
        trailing_only_offset_is_reached=bool(trailing.get("only_offset_reached", True)),
        position_adjustment_enable=bool(position_adjustment_enable),
        order_types=dict(order_types),
    )


def render_freqtrade_strategy_runtime(config: FreqtradeStrategyRuntimeConfig) -> str:
    return f"""    INTERFACE_VERSION = 3
    can_short = {config.can_short}
    timeframe = "{config.timeframe}"
    process_only_new_candles = True
    startup_candle_count = {config.startup_candle_count}
    use_exit_signal = {config.use_exit_signal}
    exit_profit_only = {config.exit_profit_only}
    ignore_roi_if_entry_signal = {config.ignore_roi_if_entry_signal}
    minimal_roi = {repr(config.minimal_roi)}
    stoploss = {config.stoploss}
    trailing_stop = {config.trailing_stop}
    trailing_stop_positive = {config.trailing_stop_positive}
    trailing_stop_positive_offset = {config.trailing_stop_positive_offset}
    trailing_only_offset_is_reached = {config.trailing_only_offset_is_reached}
    position_adjustment_enable = {config.position_adjustment_enable}
    order_types = {repr(config.order_types)}
"""
