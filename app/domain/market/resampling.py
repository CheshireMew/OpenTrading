"""Complete UTC candles for continuous crypto markets, including calendar months."""
import math
import re

from app.domain.market.constants import timeframe_to_milliseconds
from app.domain.market.candles import candle_end_ms, current_candle_open_ms

SOURCE_TIMEFRAMES = ("1d", "4h", "1h", "30m", "15m", "5m", "1m")


def synthesis_sources(symbol: str, timeframe: str) -> list[str]:
    # Session markets and provider-specific boundaries need their own calendars.
    if not re.fullmatch(r"[A-Z0-9_.-]+/[A-Z0-9_.-]+", symbol):
        return []
    if timeframe not in (*SOURCE_TIMEFRAMES, "1w", "1M"):
        return []
    target = timeframe_to_milliseconds(timeframe)
    return [source for source in SOURCE_TIMEFRAMES
            if 0 < timeframe_to_milliseconds(source) < target
            and target % timeframe_to_milliseconds(source) == 0]


def aggregate_complete(rows: list[list[float]], source: str, target: str) -> list[list[float]]:
    source_ms = timeframe_to_milliseconds(source)
    target_ms = timeframe_to_milliseconds(target)
    if not 0 < source_ms < target_ms or target_ms % source_ms:
        return []
    groups: dict[int, dict[int, list[float]]] = {}
    for row in rows:
        timestamp = int(row[0])
        if timestamp % source_ms:
            continue
        groups.setdefault(current_candle_open_ms(timestamp, target), {})[timestamp] = row
    result = []
    for start, group in sorted(groups.items()):
        required = (candle_end_ms(start, target) - start) // source_ms
        if len(group) != required or any(start + i * source_ms not in group for i in range(required)):
            continue
        ordered = [group[start + i * source_ms] for i in range(required)]
        result.append([start, ordered[0][1], max(r[2] for r in ordered),
                       min(r[3] for r in ordered), ordered[-1][4], math.fsum(r[5] for r in ordered)])
    return result
