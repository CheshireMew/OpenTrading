from __future__ import annotations

from typing import Any

from app.domain.market.technical_analysis import TechnicalAnalysis
from app.domain.market.math import percentage_change

from .binance_numbers import to_float


def build_breakout_snapshot(
    rows: list[dict[str, Any]],
    *,
    recent_window: int,
    green_window: int,
    window_bars: int,
) -> dict[str, float | None]:
    closes = [to_float(row.get("close")) for row in rows]
    opens = [to_float(row.get("open")) for row in rows]
    highs = [to_float(row.get("high")) for row in rows]
    lows = [to_float(row.get("low")) for row in rows]
    if len(closes) < 30 or any(value is None for value in closes[-30:]):
        return {}

    close_values = [value for value in closes if value is not None]
    open_values = [value for value in opens if value is not None]
    high_values = [value for value in highs if value is not None]
    low_values = [value for value in lows if value is not None]
    last_price = close_values[-1]
    ema20 = TechnicalAnalysis.calculate_ema(close_values, 20)
    rsi14 = TechnicalAnalysis.calculate_rsi(close_values, 14)
    _, _, macd_hist = TechnicalAnalysis.calculate_macd(close_values)
    recent_high = max(high_values[-recent_window:]) if len(high_values) >= recent_window else max(high_values)
    recent_low = min(low_values[-recent_window:]) if len(low_values) >= recent_window else min(low_values)
    recent_range = recent_high - recent_low
    green_pairs = list(zip(open_values[-green_window:], close_values[-green_window:]))
    max_bar_change_pct = max(
        (abs(percentage_change(close_price, open_price)) for open_price, close_price in green_pairs if open_price),
        default=None,
    )
    return {
        "bar_change_pct": percentage_change(last_price, close_values[-2]) if len(close_values) >= 2 else None,
        "window_change_pct": percentage_change(last_price, close_values[-(window_bars + 1)]) if len(close_values) > window_bars else None,
        "pullback_from_high_pct": percentage_change(last_price, recent_high),
        "range_position_pct": ((last_price - recent_low) / recent_range * 100.0) if recent_range > 0 else None,
        "ema20_gap_pct": percentage_change(last_price, ema20),
        "rsi": rsi14,
        "macd_hist": macd_hist,
        "green_ratio_pct": (sum(1 for open_price, close_price in green_pairs if close_price > open_price) / len(green_pairs) * 100.0) if green_pairs else None,
        "max_bar_change_pct": max_bar_change_pct,
    }
