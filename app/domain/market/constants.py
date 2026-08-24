"""
Centralized constants for the application to avoid magic strings.
"""
from enum import Enum

DEFAULT_ATR_PERIOD = 14
DEFAULT_VOLATILITY_PERIOD = 20

MILLISECONDS_PER_MINUTE = 60_000
MILLISECONDS_PER_HOUR = 60 * MILLISECONDS_PER_MINUTE
MILLISECONDS_PER_DAY = 24 * MILLISECONDS_PER_HOUR
MILLISECONDS_PER_WEEK = 7 * MILLISECONDS_PER_DAY
MILLISECONDS_PER_MONTH = 30 * MILLISECONDS_PER_DAY
MILLISECONDS_PER_YEAR = 365 * MILLISECONDS_PER_DAY

TIMEFRAME_UNIT_MILLISECONDS = {
    "m": MILLISECONDS_PER_MINUTE,
    "h": MILLISECONDS_PER_HOUR,
    "d": MILLISECONDS_PER_DAY,
    "w": MILLISECONDS_PER_WEEK,
    "M": MILLISECONDS_PER_MONTH,
}


def timeframe_to_milliseconds(timeframe: str) -> int:
    value = str(timeframe or "").strip()
    if value.endswith("min"):
        number, unit = value[:-3], "m"
    elif len(value) >= 2:
        number, unit = value[:-1], value[-1]
    else:
        return 0
    try:
        multiplier = int(number)
    except (TypeError, ValueError):
        return 0
    unit_ms = TIMEFRAME_UNIT_MILLISECONDS.get(unit, 0)
    return multiplier * unit_ms if multiplier > 0 else 0


def periods_per_year_for_timeframe(timeframe: str) -> int:
    interval_ms = timeframe_to_milliseconds(timeframe)
    if interval_ms <= 0:
        return 365
    return max(1, round(MILLISECONDS_PER_YEAR / interval_ms))

# Redis Key Prefixes
KEY_PREFIX_KLINE = "kline"

# Database field contracts
KLINE_SYMBOL_MAX_LENGTH = 80

class Timeframe(str, Enum):
    M1 = '1m'
    M5 = '5m'
    M15 = '15m'
    M30 = '30m'
    H1 = '1h'
    H4 = '4h'
    D1 = '1d'
    W1 = '1w'
    M1_MONTH = '1M'
