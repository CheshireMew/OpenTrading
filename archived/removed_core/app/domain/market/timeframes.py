from __future__ import annotations

from datetime import timedelta


TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}


def timeframe_to_minutes(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"不支持的时间周期: {timeframe}")
    return TIMEFRAME_MINUTES[timeframe]


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    return timedelta(minutes=timeframe_to_minutes(timeframe))
