from __future__ import annotations

from typing import Iterable

STYLE_PROFILES: dict[str, dict[str, float]] = {
    "Scalping": {"stop_multiplier": 0.85, "min_stop_pct": 0.008, "risk_pct": 0.006},
    "Intraday": {"stop_multiplier": 1.0, "min_stop_pct": 0.012, "risk_pct": 0.01},
    "Swing": {"stop_multiplier": 1.35, "min_stop_pct": 0.018, "risk_pct": 0.012},
}

STRATEGY_PROFILES: dict[str, dict[str, float]] = {
    "最大收益": {"reward_multiplier": 2.4},
    "稳健突破": {"reward_multiplier": 1.8},
    "回撤反转": {"reward_multiplier": 2.0},
}

SIDE_RULES: dict[str, dict[str, float]] = {
    "long": {"rsi_min": 42.0, "rsi_max": 74.0, "macd_hist_threshold": 0.0},
    "short": {"rsi_min": 26.0, "rsi_max": 58.0, "macd_hist_threshold": 0.0},
}

BACKTEST_FIXED_STYLE = "Scalping"
BACKTEST_FIXED_STRATEGY = "最大收益"


def style_profile(style: str) -> dict[str, float]:
    return STYLE_PROFILES.get(style, STYLE_PROFILES["Intraday"])


def strategy_profile(strategy: str) -> dict[str, float]:
    return STRATEGY_PROFILES.get(strategy, STRATEGY_PROFILES["最大收益"])


def resolve_rule_side(*, current_price: float, ema: float, rsi: float, macd_hist: float) -> str | None:
    long_rule = SIDE_RULES["long"]
    if (
        current_price > ema
        and macd_hist >= long_rule["macd_hist_threshold"]
        and long_rule["rsi_min"] <= rsi <= long_rule["rsi_max"]
    ):
        return "long"
    short_rule = SIDE_RULES["short"]
    if (
        current_price < ema
        and macd_hist <= short_rule["macd_hist_threshold"]
        and short_rule["rsi_min"] <= rsi <= short_rule["rsi_max"]
    ):
        return "short"
    return None


def build_rule_trade_plan(
    *,
    side: str,
    entry_price: float,
    atr: float,
    support_price: float,
    resistance_price: float,
    style: str,
    strategy: str,
) -> dict[str, float]:
    if entry_price <= 0 or atr <= 0:
        raise ValueError("entry_price 和 atr 必须为正数")

    style_values = style_profile(style)
    strategy_values = strategy_profile(strategy)
    stop_distance = max(
        atr * style_values["stop_multiplier"],
        entry_price * style_values["min_stop_pct"],
    )
    if side == "long":
        stop = min(entry_price - stop_distance, support_price)
        target = entry_price + abs(entry_price - stop) * strategy_values["reward_multiplier"]
    elif side == "short":
        stop = max(entry_price + stop_distance, resistance_price)
        target = entry_price - abs(entry_price - stop) * strategy_values["reward_multiplier"]
    else:
        raise ValueError(f"不支持的方向: {side}")
    return {
        "entry": entry_price,
        "stop": stop,
        "target": target,
        "risk_reward": abs(target - entry_price) / abs(entry_price - stop),
    }


def rolling_low(candles: Iterable[list[float]], lookback: int) -> float:
    window = list(candles)[-lookback:]
    if not window:
        raise ValueError("rolling_low 需要至少一根K线")
    return min(float(kline[3]) for kline in window)


def rolling_high(candles: Iterable[list[float]], lookback: int) -> float:
    window = list(candles)[-lookback:]
    if not window:
        raise ValueError("rolling_high 需要至少一根K线")
    return max(float(kline[2]) for kline in window)
