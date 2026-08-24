from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.services.persistence_ports import KlineStorePort
from app.services.market.history_ranges import collect_missing_ranges
from app.services.market.symbol_routing import MarketSymbolRouting
from config import settings
from utils.logger import logger


@dataclass(frozen=True, slots=True)
class OhlcvRangeResult:
    rows: list[list[float]]
    missing_ranges: list[tuple[int, int]]

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


class KlineRangeLoader:
    def __init__(self, *, kline_store: KlineStorePort, symbol_routing: MarketSymbolRouting) -> None:
        self.kline_store = kline_store
        self.symbol_routing = symbol_routing

    def load_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        persist_klines: Callable[[str, str, list[list[float]]], None] | None = None,
    ) -> OhlcvRangeResult:
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        end_ts_exclusive = end_ts + 1
        range_start = time.time()
        cached_klines: list[list[float]] = []
        new_data: list[list[float]] = []
        missing_ranges: list[tuple[int, int]] = []
        storage_symbol = self.symbol_routing.storage_symbol(symbol)

        try:
            try:
                cached_klines = self.kline_store.get_range(storage_symbol, timeframe, start_ts, end_ts)
            except Exception as exc:
                logger.error(f"缓存读取失败，改用交易所数据: {exc}")
                rows = self.fetch_gap(symbol, timeframe, start_ts, end_ts_exclusive)
                return self._range_result(
                    rows=rows,
                    timeframe=timeframe,
                    start_ts=start_ts,
                    end_ts_exclusive=end_ts_exclusive,
                )

            logger.info(f"缓存命中: {len(cached_klines)} 条 ({storage_symbol})")

            missing_ranges = collect_missing_ranges(
                cached_klines=cached_klines,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts_exclusive=end_ts_exclusive,
            )
            for gap_start, gap_end in missing_ranges:
                new_data.extend(self.fetch_gap(symbol, timeframe, gap_start, gap_end))

            if new_data:
                logger.info(f"下载新数据: {len(new_data)} 条")
                try:
                    if persist_klines:
                        persist_klines(storage_symbol, timeframe, new_data)
                    else:
                        self.kline_store.save(storage_symbol, timeframe, new_data)
                except Exception as exc:
                    logger.warning(f"历史 K 线回写缓存失败: {exc}")

            merged = {k[0]: k for k in cached_klines}
            for row in new_data:
                merged[row[0]] = row

            final_data = sorted(merged.values(), key=lambda x: x[0])
            return self._range_result(
                rows=[row for row in final_data if start_ts <= row[0] <= end_ts],
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts_exclusive=end_ts_exclusive,
            )
        finally:
            elapsed = time.time() - range_start
            logger.debug(
                f"[metrics] load_ohlcv_range symbol={symbol} tf={timeframe} "
                f"cached={len(cached_klines)} new={len(new_data)} gaps={len(missing_ranges)} elapsed={elapsed:.2f}s"
            )

    def load_cached_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> OhlcvRangeResult:
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        range_start = time.time()
        try:
            rows = self.kline_store.get_range(self.symbol_routing.storage_symbol(symbol), timeframe, start_ts, end_ts)
            return self._range_result(
                rows=rows,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts_exclusive=end_ts + 1,
            )
        finally:
            elapsed = time.time() - range_start
            logger.debug(
                f"[metrics] load_cached_ohlcv_range symbol={symbol} tf={timeframe} "
                f"elapsed={elapsed:.2f}s"
            )

    def load_live_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> OhlcvRangeResult:
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)
        range_start = time.time()
        try:
            rows = self.fetch_gap(symbol, timeframe, start_ts, end_ts + 1)
            return self._range_result(
                rows=rows,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts_exclusive=end_ts + 1,
            )
        finally:
            elapsed = time.time() - range_start
            logger.debug(
                f"[metrics] load_live_ohlcv_range symbol={symbol} tf={timeframe} "
                f"elapsed={elapsed:.2f}s"
            )

    def fetch_gap(self, symbol: str, timeframe: str, since: int, until: int) -> list[list[float]]:
        data: list[list[float]] = []
        current_since = since
        task_start = time.time()
        fetch_symbol = self.symbol_routing.fetch_symbol(symbol)
        gateway = self.symbol_routing.gateway_for_symbol(symbol)

        while current_since < until:
            limit = settings.EXCHANGE_FETCH_LIMIT
            batch, _attempts = gateway.fetch_ohlcv(
                fetch_symbol,
                timeframe,
                since=current_since,
                limit=limit,
            )

            if not batch:
                break

            filtered = [row for row in batch if row[0] < until]
            if not filtered:
                break

            data.extend(filtered)
            last_ts = filtered[-1][0]
            if last_ts < current_since:
                break

            current_since = last_ts + 1
            gateway.sleep_for_rate_limit()

            if len(batch) < limit:
                break

            if time.time() - task_start > gateway.max_task_seconds:
                logger.warning(f"[_fetch_gap] 超时终止 symbol={symbol} tf={timeframe} since={since} until={until}")
                break

        return data

    def _range_result(
        self,
        *,
        rows: list[list[float]],
        timeframe: str,
        start_ts: int,
        end_ts_exclusive: int,
    ) -> OhlcvRangeResult:
        clean_rows = [row for row in rows if row and start_ts <= row[0] < end_ts_exclusive]
        return OhlcvRangeResult(
            rows=sorted(clean_rows, key=lambda row: row[0]),
            missing_ranges=collect_missing_ranges(
                cached_klines=clean_rows,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts_exclusive=end_ts_exclusive,
            ),
        )
