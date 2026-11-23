from __future__ import annotations

from datetime import datetime, timezone

from signal_lab.core.market import Candle, CandleSeries, timeframe_delta


def resample_completed(series: CandleSeries, target_timeframe: str) -> CandleSeries:
    source_step = timeframe_delta(series.timeframe)
    target_step = timeframe_delta(target_timeframe)
    if target_step < source_step or target_step % source_step:
        raise ValueError("target timeframe must be an integer multiple of source timeframe")
    expected_count = int(target_step / source_step)
    buckets: dict[datetime, list[Candle]] = {}
    for candle in series.candles:
        epoch = int(candle.opened_at.timestamp())
        bucket_epoch = epoch - (epoch % int(target_step.total_seconds()))
        bucket = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
        buckets.setdefault(bucket, []).append(candle)

    resampled: list[Candle] = []
    for bucket, items in sorted(buckets.items()):
        if len(items) != expected_count:
            continue
        expected_times = [bucket + source_step * index for index in range(expected_count)]
        if [item.opened_at for item in items] != expected_times:
            continue
        resampled.append(
            Candle(
                opened_at=bucket,
                open=items[0].open,
                high=max(item.high for item in items),
                low=min(item.low for item in items),
                close=items[-1].close,
                volume=sum(item.volume for item in items),
            )
        )
    return CandleSeries(
        symbol=series.symbol,
        timeframe=target_timeframe,
        price_source=series.price_source,
        venue=series.venue,
        candles=tuple(resampled),
    )


def true_ranges(series: CandleSeries) -> list[float]:
    values: list[float] = []
    previous_close: float | None = None
    for candle in series.candles:
        value = candle.high - candle.low
        if previous_close is not None:
            value = max(value, abs(candle.high - previous_close), abs(candle.low - previous_close))
        values.append(value)
        previous_close = candle.close
    return values


def atr(series: CandleSeries, period: int = 14) -> list[float | None]:
    if period <= 0:
        raise ValueError("ATR period must be positive")
    ranges = true_ranges(series)
    output: list[float | None] = [None] * len(ranges)
    running = 0.0
    for index, value in enumerate(ranges):
        running += value
        if index >= period:
            running -= ranges[index - period]
        if index >= period - 1:
            output[index] = running / period
    return output
