"""Candle time boundaries and observation metadata, independent of transport."""
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.market.constants import timeframe_to_milliseconds


def candle_end_ms(timestamp: int, timeframe: str) -> int:
    if timeframe.endswith("M") and timeframe[:-1].isdigit():
        start = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
        months = start.year * 12 + start.month - 1 + int(timeframe[:-1])
        return int(start.replace(year=months // 12, month=months % 12 + 1, day=1).timestamp() * 1000)
    interval = timeframe_to_milliseconds(timeframe)
    if interval <= 0:
        raise ValueError(f"Unsupported candle timeframe: {timeframe}")
    return timestamp + interval


def closed_candles(rows: list[list[float]], timeframe: str, observed_at_ms: int) -> list[list[float]]:
    return [row for row in rows if candle_end_ms(int(row[0]), timeframe) <= observed_at_ms]


def current_candle_open_ms(now_ms: int, timeframe: str) -> int:
    if timeframe.endswith("M") and timeframe[:-1].isdigit():
        now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
        months = now.year * 12 + now.month - 1
        months -= months % int(timeframe[:-1])
        return int(datetime(months // 12, months % 12 + 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    interval = timeframe_to_milliseconds(timeframe)
    if interval <= 0:
        raise ValueError(f"Unsupported candle timeframe: {timeframe}")
    origin = 345_600_000 if timeframe.endswith("w") else 0  # Monday, 1970-01-05.
    return (now_ms - origin) // interval * interval + origin


@dataclass(frozen=True, slots=True)
class RecentCandles:
    rows: list[list[float]]
    observed_at_ms: int | None
    source: str

    def fresh(self, now_ms: int, max_age_seconds: float) -> bool:
        return self.observed_at_ms is not None and -5_000 <= now_ms - self.observed_at_ms <= max_age_seconds * 1000
