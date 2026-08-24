from __future__ import annotations

from app.domain.market.constants import timeframe_to_milliseconds


def merge_missing_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []

    merged: list[tuple[int, int]] = []
    for range_start, range_end in sorted(ranges):
        if range_start >= range_end:
            continue
        if not merged:
            merged.append((range_start, range_end))
            continue
        last_start, last_end = merged[-1]
        if range_start <= last_end:
            merged[-1] = (last_start, max(last_end, range_end))
            continue
        merged.append((range_start, range_end))
    return merged


def collect_missing_ranges(
    *,
    cached_klines: list[list[float]],
    timeframe: str,
    start_ts: int,
    end_ts_exclusive: int,
) -> list[tuple[int, int]]:
    if start_ts >= end_ts_exclusive:
        return []
    if not cached_klines:
        return [(start_ts, end_ts_exclusive)]

    timeframe_ms = timeframe_to_milliseconds(timeframe)
    missing_ranges: list[tuple[int, int]] = []
    sorted_rows = sorted(cached_klines, key=lambda row: row[0])
    first_cached = int(sorted_rows[0][0])
    last_cached = int(sorted_rows[-1][0])

    if start_ts < first_cached:
        missing_ranges.append((start_ts, first_cached))

    if timeframe_ms > 0:
        for previous_row, current_row in zip(sorted_rows, sorted_rows[1:]):
            previous_ts = int(previous_row[0])
            current_ts = int(current_row[0])
            expected_next_ts = previous_ts + timeframe_ms
            if current_ts <= expected_next_ts:
                continue
            gap_start = max(start_ts, expected_next_ts)
            gap_end = min(end_ts_exclusive, current_ts)
            if gap_start < gap_end:
                missing_ranges.append((gap_start, gap_end))

    tail_start = last_cached + timeframe_ms if timeframe_ms > 0 else last_cached + 1
    if end_ts_exclusive > tail_start:
        missing_ranges.append((tail_start, end_ts_exclusive))

    return merge_missing_ranges(missing_ranges)


def is_recent_cache_usable(
    *,
    cached: list[list[float]],
    timeframe: str,
    limit: int,
    now_ms: int,
) -> bool:
    if len(cached) < limit:
        return False
    timeframe_ms = timeframe_to_milliseconds(timeframe)
    if timeframe_ms <= 0:
        return False
    latest_open_ts = int(cached[-1][0])
    return latest_open_ts + (timeframe_ms * 2) > now_ms
