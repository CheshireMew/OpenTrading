from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import time
from app.domain.market.candles import closed_candles

from app.services.market.history_ranges import collect_missing_ranges
from app.application.persistence_ports import KlineStorePort
from config import settings


def merge_ohlcv_rows(
    *batches: list[list[float]],
    start_ts: int | None = None,
    end_ts_exclusive: int | None = None,
) -> list[list[float]]:
    merged: dict[int, list[float]] = {}
    for batch in batches:
        for row in batch:
            if not row:
                continue
            timestamp = int(row[0])
            if start_ts is not None and timestamp < start_ts:
                continue
            if end_ts_exclusive is not None and timestamp >= end_ts_exclusive:
                continue
            merged[timestamp] = row
    return [merged[key] for key in sorted(merged)]


@dataclass(frozen=True, slots=True)
class OhlcvRangeResult:
    rows: list[list[float]]
    missing_ranges: list[tuple[int, int]]
    cached_rows: list[list[float]] = field(default_factory=list)
    fetched_rows: list[list[float]] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing_ranges

    def require_complete(self, *, symbol: str, timeframe: str) -> list[list[float]]:
        if self.complete:
            return self.rows
        ranges = ", ".join(f"{start}-{end}" for start, end in self.missing_ranges)
        raise RuntimeError(
            f"Incomplete OHLCV history for {symbol} {timeframe}; missing ranges: {ranges}"
        )


class HistoryRangeCoordinator:
    """The only owner of cached OHLCV range hydration and merge semantics."""

    def __init__(self, store: KlineStorePort, *, storage_runner=None) -> None:
        self._store = store
        self._storage_runner = storage_runner

    async def _run_storage(self, operation):
        if self._storage_runner is not None:
            return await self._storage_runner(operation)
        return operation()

    def load(
        self,
        *,
        storage_symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
        fetch_gap: Callable[[int, int], list[list[float]]],
        persist: Callable[[str, str, list[list[float]]], None] | None = None,
        fallback_on_cache_error: bool = False,
        cached_rows: list[list[float]] | None = None,
        coalesce_gaps: bool = False,
        refresh_tail: bool = False,
        missing_ranges: Callable[[list[list[float]]], list[tuple[int, int]]] | None = None,
    ) -> OhlcvRangeResult:
        cached = list(cached_rows) if cached_rows is not None else self._read_cached(
            storage_symbol=storage_symbol,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
            fallback_on_error=fallback_on_cache_error,
        )
        missing = missing_ranges(cached) if missing_ranges else self._missing(cached, timeframe, start_ts, end_ts_exclusive)
        if refresh_tail and cached:
            missing.append((max(start_ts, int(cached[-1][0])), end_ts_exclusive))
        if coalesce_gaps and missing:
            # Exchange holidays are not missing index candles. A single range
            # request also avoids one upstream download per weekend.
            missing = [(min(start for start, _ in missing), max(end for _, end in missing))]
        observed_at = int(time.time() * 1000)
        fetched = closed_candles([
            row
            for gap_start, gap_end in missing
            for row in fetch_gap(gap_start, gap_end)
        ], timeframe, observed_at)
        self._persist(storage_symbol, timeframe, fetched, persist)
        result = self._result(cached, fetched, timeframe, start_ts, end_ts_exclusive)
        if missing_ranges is not None:
            return OhlcvRangeResult(result.rows, missing_ranges(result.rows), result.cached_rows, result.fetched_rows)
        return result

    async def load_async(
        self,
        *,
        storage_symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
        fetch_gap: Callable[[int, int], Awaitable[list[list[float]]]],
        persist: Callable[[str, str, list[list[float]]], None] | None = None,
        fallback_on_cache_error: bool = False,
        cached_rows: list[list[float]] | None = None,
    ) -> OhlcvRangeResult:
        cached = list(cached_rows) if cached_rows is not None else await self._run_storage(lambda: self._read_cached(
            storage_symbol=storage_symbol,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
            fallback_on_error=fallback_on_cache_error,
        ))
        missing = self._missing(cached, timeframe, start_ts, end_ts_exclusive)
        fetched: list[list[float]] = []
        observed_at = int(time.time() * 1000)
        for gap_start, gap_end in missing:
            fetched.extend(await fetch_gap(gap_start, gap_end))
        fetched = closed_candles(fetched, timeframe, observed_at)
        await self._run_storage(lambda: self._persist(storage_symbol, timeframe, fetched, persist))
        return self._result(cached, fetched, timeframe, start_ts, end_ts_exclusive)

    def read_cached(
        self,
        *,
        storage_symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
    ) -> OhlcvRangeResult:
        cached = self._read_cached(
            storage_symbol=storage_symbol,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
            fallback_on_error=False,
        )
        return self._result(cached, [], timeframe, start_ts, end_ts_exclusive)

    def from_live_rows(
        self,
        *,
        rows: list[list[float]],
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
    ) -> OhlcvRangeResult:
        return self._result([], closed_candles(rows, timeframe, int(time.time() * 1000)), timeframe, start_ts, end_ts_exclusive)

    def _read_cached(
        self,
        *,
        storage_symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
        fallback_on_error: bool,
    ) -> list[list[float]]:
        try:
            return self._store.get_range(
                storage_symbol,
                timeframe,
                start_ts,
                max(start_ts, end_ts_exclusive - 1),
            )
        except Exception:
            if fallback_on_error:
                return []
            raise

    def _persist(
        self,
        storage_symbol: str,
        timeframe: str,
        rows: list[list[float]],
        persist: Callable[[str, str, list[list[float]]], None] | None,
    ) -> None:
        if not rows:
            return
        save = persist or self._store.save
        batch_size = max(int(settings.KLINE_UPSERT_BATCH_SIZE), 1)
        for start in range(0, len(rows), batch_size):
            save(storage_symbol, timeframe, rows[start:start + batch_size])

    @staticmethod
    def _missing(
        rows: list[list[float]],
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
    ) -> list[tuple[int, int]]:
        return collect_missing_ranges(
            cached_klines=rows,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
        )

    @classmethod
    def _result(
        cls,
        cached: list[list[float]],
        fetched: list[list[float]],
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
    ) -> OhlcvRangeResult:
        rows = merge_ohlcv_rows(
            cached,
            fetched,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
        )
        return OhlcvRangeResult(
            rows=rows,
            missing_ranges=cls._missing(rows, timeframe, start_ts, end_ts_exclusive),
            cached_rows=list(cached),
            fetched_rows=list(fetched),
        )
