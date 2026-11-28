"""Shared index periods, public-feed history and bounded process-wide caches."""
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import time
from zoneinfo import ZoneInfo

from app.contracts.chart_workspace import ChartBar, ChartBars, ChartQuote
from app.domain.market.candles import candle_end_ms, current_candle_open_ms
from app.domain.market.constants import timeframe_to_milliseconds
from app.domain.market.index_catalog import INDEX_CATALOG
from app.domain.market.index_history_policy import live_index_rows, live_start_ms, utc_datetime
from app.infra.executor import run_external_io, run_database
from app.infra.market_data.index_chart import IndexChartClient
from app.infra.market_data.exchange import MarketDataError
from app.services.chart_index_catalog import index_symbol, RETENTION

DAY = 86_400_000


def period_open(stamp, timeframe, offset=0):
    return current_candle_open_ms(int(stamp) - offset, timeframe) + offset


def aggregate(rows, timeframe, offset=0):
    buckets = {}
    for row in sorted(rows, key=lambda row: row[0]):
        stamp = period_open(row[0], timeframe, offset)
        bucket = buckets.get(stamp)
        if bucket is None:
            buckets[stamp] = [stamp, *row[1:5], 0.0]
        else:
            bucket[2], bucket[3], bucket[4] = max(bucket[2], row[2]), min(bucket[3], row[3]), row[4]
    return list(buckets.values())


class ChartIndexMarket:
    def __init__(self, index, store=None, client=None):
        self.index, self.store = index, store
        self.client = client or IndexChartClient()
        self._tasks = {}
        self._cache = OrderedDict()
        self._slots = asyncio.Semaphore(3)

    async def _history(self, symbol, interval, start, end):
        key = (symbol, interval, start, end)
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            self._cache.move_to_end(key)
            return cached[1]
        task = self._tasks.get(key)
        if task is None:
            async def load():
                async with self._slots:
                    rows = live_index_rows(symbol,await run_external_io(lambda: self._fetch_history(symbol, interval, start, end)))
                    # Persist the source period as soon as it is obtained,
                    # including minute observations used only for watch quotes
                    # and hourly observations used to build four-hour candles.
                    if self.store is not None and interval != "1d":
                        timeframe = "1h" if interval == "60m" else interval
                        cutoff = min(end, int(time.time() * 1000) - 15 * 60_000)
                        confirmed = [row for row in rows if row[0] >= start and
                            candle_end_ms(int(row[0]), timeframe) <= cutoff]
                        if confirmed:
                            await run_database(lambda: self.store.save(INDEX_CATALOG[symbol].storage_symbol, timeframe, confirmed))
                    return rows
            task = asyncio.create_task(load())
            self._tasks[key] = task
            def finished(completed):
                self._tasks.pop(key, None)
                if not completed.cancelled() and completed.exception() is None:
                    self._cache[key] = (time.monotonic() + 30, completed.result())
                    while len(self._cache) > 32 or sum(len(value[1]) for value in self._cache.values()) > 32_000:
                        self._cache.popitem(last=False)
            task.add_done_callback(finished)
        return await asyncio.shield(task)

    def _fetch_history(self, symbol, interval, start, end):
        return self.client.history(symbol, interval, start, end)

    async def _daily(self, symbol, lower, upper, now):
        first_day = utc_datetime(lower).date()
        today = current_candle_open_ms(now, "1d")
        # A backward page ends at the next bar's open minus one millisecond.
        # It still includes the preceding completed session; only replay uses
        # closeTime as its historical cutoff.
        last_day = utc_datetime(min(upper, today - 1)).date()
        rows, source, close_only = [], "yahoo-finance", False
        # Read the shared daily store before hydrating missing sessions. The
        # source service merges real index archives when one feed is partial.
        native_daily = self.index is None
        if native_daily:
            try:
                rows = await self._history(symbol, "1d", max(lower - DAY, live_start_ms(symbol)), upper // 30_000 * 30_000)
            except MarketDataError:
                native_daily = False
                if self.index is None:
                    raise
        if not native_daily and first_day <= last_day:
            result = await self.index.get_history_async(symbol=symbol, timeframe="1d",
                start_date=first_day.isoformat(), end_date=last_day.isoformat())
            if result.source == "none":
                raise MarketDataError(f"{index_symbol(symbol).metadata['name_zh']} 日线数据暂不可用，请重试")
            rows = [row.as_row() for row in result.data]
            source, close_only = result.source, getattr(result, "is_close_only", False)
        live = upper >= today and upper >= now - 60_000
        rows = [row for row in rows if row[0] <= upper and (row[0] < today or live)]
        if native_daily and self.store is not None:
            confirmed = [row for row in rows if candle_end_ms(int(row[0]), "1d") <= min(upper, now)]
            if confirmed:
                await run_database(lambda: self.store.save(INDEX_CATALOG[symbol].storage_symbol, "1d", confirmed))
        if live and not native_daily:
            try:
                recent = await self._history(symbol, "1d", today - 7 * DAY, now // 30_000 * 30_000)
                current = [row for row in recent if row[0] >= today]
                rows = list({row[0]: row for row in [*rows, *current]}.values())
                if current:
                    source += "+yahoo-finance"
            except MarketDataError:
                if not rows:
                    raise
        return live_index_rows(symbol,rows), source, close_only

    async def bars(self, symbol, timeframe, limit, start, end):
        now = int(time.time() * 1000)
        info = index_symbol(symbol)
        offset = info.metadata["candle_offset_ms"].get(timeframe, 0)
        close_only_times = set()
        live_start = live_start_ms(symbol)
        if end < live_start:
            return ChartBars(symbol=info,timeframe=timeframe,bars=[],source="not-launched")
        if timeframe in {"1d", "1w", "1M"}:
            span = limit * {"1d": 3, "1w": 10, "1M": 45}[timeframe] * DAY + 14 * DAY
            lower = max(period_open(start if start is not None else end - span, timeframe),live_start)
            upper = min(end, lower + span) if start is not None else end
            rows, source, _page_close_only = await self._daily(symbol, lower, upper, now)
            # Early published records can contain only closes even when recent
            # sessions have full OHLC. This is a property of those observations,
            # not a capability change for the entire index while paging.
            close_only_times = {period_open(row[0], timeframe) for row in rows
                if row[1] == row[2] == row[3] == row[4] and not row[5]}
            rows = aggregate(rows, timeframe) if timeframe != "1d" else rows
            # A week/month containing a close-only day cannot claim complete
            # period OHLC. Preserve its actual last close without invented ranges.
            rows = [[row[0], row[4], row[4], row[4], row[4], 0.0]
                if row[0] in close_only_times else row for row in rows]
        else:
            source = "yahoo-finance"
            interval = "60m" if timeframe in {"1h", "4h"} else timeframe
            duration = timeframe_to_milliseconds(timeframe)
            retention = now - RETENTION[timeframe] * DAY
            span = min(7 if timeframe == "1m" else 59 if timeframe.endswith("m") else 365,
                max(7, limit * duration // DAY * 3 + 7)) * DAY
            lower = max(start if start is not None else end - span, live_start)
            upper = min(end, lower + span) if start is not None else end
            storage = INDEX_CATALOG[symbol].storage_symbol
            rows = []
            if self.store is not None:
                if start is None:
                    # A saved range can be months/years behind the vendor's
                    # rolling window. Do not stop at an empty seven-day page.
                    rows = await run_database(lambda: self.store.get_before(storage, timeframe, end + 1, limit))
                else:
                    rows = await run_database(lambda: self.store.get_range(storage, timeframe, lower, upper))
            rows = live_index_rows(symbol,rows)
            cached_start = min((int(row[0]) for row in rows), default=None)
            if upper >= retention:
                fetch_start = max(period_open(lower, timeframe, offset), retention)
                fetched = await self._history(symbol, interval, fetch_start, min(upper, now) // 30_000 * 30_000)
                if timeframe == "4h":
                    fetched = aggregate(fetched, timeframe, offset)
                rows = list({row[0]: row for row in [*rows, *fetched]}.values())
                if self.store is not None and timeframe == "4h":
                    confirmed = [row for row in fetched if row[0] >= fetch_start and
                        candle_end_ms(int(row[0]), timeframe) <= min(upper, now - 15 * 60_000)]
                    if confirmed:
                        await run_database(lambda: self.store.save(storage, timeframe, confirmed))
            else:
                source = "cache"
            info.metadata = {**info.metadata, "upstream_history_start": max(int(retention), 0),
                "history_start": max(min(int(retention), cached_start) if cached_start is not None else int(retention), 0)}
            if cached_start is not None:
                info.metadata["cached_history_start"] = cached_start
        rows = sorted((row for row in rows if row[0] <= end and (start is None or row[0] >= start)), key=lambda row: row[0])
        selected = rows[:limit] if start is not None else rows[-limit:]
        bars = [ChartBar(time=int(row[0]), open=row[1], high=row[2], low=row[3], close=row[4], volume=0,
            closeOnly=int(row[0]) in close_only_times,
            closeTime=candle_end_ms(int(row[0]), timeframe), closed=candle_end_ms(int(row[0]), timeframe) <=
                now - (15 * 60_000 if timeframe in RETENTION else 0)) for row in selected]
        return ChartBars(symbol=info, timeframe=timeframe, bars=bars, source=source)

    async def quote(self, symbol):
        now = int(time.time() * 1000)
        info = index_symbol(symbol)
        today = current_candle_open_ms(now, "1d")
        daily, ticks = await asyncio.gather(
            self.bars(symbol, "1d", 10, None, now),
            self._history(symbol, "1m", today - 6 * DAY, now // 30_000 * 30_000))
        if not daily.bars:
            raise MarketDataError(f"{info.metadata['name_zh']} 报价暂不可用")
        price = ticks[-1][4] if ticks else daily.bars[-1].close
        updated = int(ticks[-1][0]) if ticks else daily.bars[-1].time
        # Daily timestamps name exchange-local session dates at UTC midnight.
        # A Chinese 09:30 tick and a late New York tick must compare against the
        # previous local session, not against the current UTC date's close.
        session = datetime.fromtimestamp(updated / 1000, ZoneInfo(info.timezone))
        session_day = int(datetime(session.year, session.month, session.day, tzinfo=timezone.utc).timestamp() * 1000)
        previous = [bar for bar in daily.bars if bar.time < session_day]
        prior = previous[-1].close if previous else daily.bars[0].close
        return ChartQuote(id=info.id, price=price, change=price-prior, change_pct=(price/prior-1)*100,
            basis="延迟行情 · Yahoo Finance", updated_at=updated)

    async def close(self):
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._cache.clear()
        close = getattr(self.client, "close", None)
        if close is not None:
            await run_external_io(close)
