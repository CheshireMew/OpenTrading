from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal


PriceSource = Literal["spot", "perpetual"]


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def timeframe_delta(timeframe: str) -> timedelta:
    units = {"m": 60, "h": 3600, "d": 86400}
    if len(timeframe) < 2 or timeframe[-1] not in units:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    try:
        count = int(timeframe[:-1])
    except ValueError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe}") from exc
    if count <= 0:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return timedelta(seconds=count * units[timeframe[-1]])


@dataclass(frozen=True, slots=True)
class Candle:
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", ensure_utc(self.opened_at))
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid OHLC bounds")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")

    def closed_at(self, timeframe: str) -> datetime:
        return self.opened_at + timeframe_delta(timeframe)


@dataclass(frozen=True, slots=True)
class MissingRange:
    start: datetime
    end: datetime
    missing_bars: int


@dataclass(frozen=True, slots=True)
class CandleSeries:
    symbol: str
    timeframe: str
    price_source: PriceSource
    venue: str
    candles: tuple[Candle, ...]
    missing_ranges: tuple[MissingRange, ...] = ()

    def __post_init__(self) -> None:
        timeframe_delta(self.timeframe)
        times = [item.opened_at for item in self.candles]
        if times != sorted(times):
            raise ValueError("candles must be sorted by opened_at")
        if len(times) != len(set(times)):
            raise ValueError("duplicate candle timestamps")
        expected_missing = self.detect_missing_ranges()
        if self.missing_ranges and self.missing_ranges != expected_missing:
            raise ValueError("missing_ranges do not match candle timestamps")
        if not self.missing_ranges and expected_missing:
            object.__setattr__(self, "missing_ranges", expected_missing)

    def detect_missing_ranges(self) -> tuple[MissingRange, ...]:
        step = timeframe_delta(self.timeframe)
        missing: list[MissingRange] = []
        for previous, current in zip(self.candles, self.candles[1:]):
            gap = current.opened_at - previous.opened_at
            if gap > step:
                count = int(gap / step) - 1
                missing.append(
                    MissingRange(
                        start=previous.opened_at + step,
                        end=current.opened_at - step,
                        missing_bars=count,
                    )
                )
        return tuple(missing)

    @property
    def data_hash(self) -> str:
        digest = sha256()
        digest.update(f"{self.symbol}|{self.timeframe}|{self.price_source}|{self.venue}".encode())
        for candle in self.candles:
            digest.update(
                (
                    f"{candle.opened_at.isoformat()}|{candle.open:.12g}|{candle.high:.12g}|"
                    f"{candle.low:.12g}|{candle.close:.12g}|{candle.volume:.12g}"
                ).encode()
            )
        return digest.hexdigest()
