from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from app.infra.cache import RedisService
from app.domain.market.constants import KEY_PREFIX_KLINE
from app.application.persistence_ports import KlineStorePort
from app.services.market.exchange_kline_fetcher import ExchangeKlineFetcher
from app.services.market.exchange_gateway import ExchangeGateway
from app.domain.market.constants import timeframe_to_milliseconds
from app.services.market.history_ranges import is_recent_cache_usable
from app.services.market.history_range_coordinator import (
    HistoryRangeCoordinator,
    OhlcvRangeResult,
    merge_ohlcv_rows,
)
from app.services.market.symbol_routing import MarketSymbolRouting
from config import settings
from utils.logger import logger


class MarketDataService:
    def __init__(
        self,
        exchange_gateway: ExchangeGateway | None = None,
        kline_store: KlineStorePort | None = None,
        cache_service: RedisService | None = None,
    ) -> None:
        if exchange_gateway is None or kline_store is None:
            raise ValueError("MarketDataService 需要显式注入 exchange_gateway 和 kline_store")
        self.exchange_gateway = exchange_gateway
        self.kline_store = kline_store
        self.cache_service = cache_service
        self.symbol_routing = MarketSymbolRouting(exchange_gateway)
        self.history_ranges = HistoryRangeCoordinator(kline_store)
        self.exchange_history = ExchangeKlineFetcher(self.symbol_routing)

    def get_kline_data(
        self,
        symbol: str,
        timeframe: str = settings.TIMEFRAME,
        limit: int = settings.LIMIT,
    ) -> list[list[float]]:
        start_time = time.time()
        cache_hit = False
        attempts = 0
        try:
            storage_symbol = self.symbol_routing.storage_symbol(symbol)
            fetch_symbol = self.symbol_routing.fetch_symbol(symbol)
            gateway = self.symbol_routing.gateway_for_symbol(symbol)
            cache_key = f"{KEY_PREFIX_KLINE}:{storage_symbol}:{timeframe}:{limit}"
            cached_data = self.cache_service.get(cache_key) if self.cache_service is not None else None
            if cached_data:
                cache_hit = True
                return cached_data

            data, attempts = gateway.fetch_ohlcv(fetch_symbol, timeframe, limit=limit)
            if data and self.cache_service is not None:
                self.cache_service.set(cache_key, data, ttl=settings.REDIS_KLINE_TTL)
            return data
        except Exception as e:
            logger.error(f"K线数据获取错误 (Redis/Exchange): {e}")
            fetch_symbol = self.symbol_routing.fetch_symbol(symbol)
            gateway = self.symbol_routing.gateway_for_symbol(symbol)
            data, attempts = gateway.fetch_ohlcv(fetch_symbol, timeframe, limit=limit)
            return data
        finally:
            elapsed = time.time() - start_time
            logger.debug(
                f"[metrics] get_kline_data symbol={symbol} tf={timeframe} limit={limit} "
                f"cache_hit={cache_hit} attempts={attempts} elapsed={elapsed:.2f}s"
            )

    def get_live_kline_data(
        self,
        symbol: str,
        timeframe: str = settings.TIMEFRAME,
        limit: int = settings.LIMIT,
        *,
        max_retries: int | None = None,
    ) -> list[list[float]]:
        start_time = time.time()
        attempts = 0
        try:
            storage_symbol = self.symbol_routing.storage_symbol(symbol)
            fetch_symbol = self.symbol_routing.fetch_symbol(symbol)
            gateway = self.symbol_routing.gateway_for_symbol(symbol)
            cache_key = f"{KEY_PREFIX_KLINE}:{storage_symbol}:{timeframe}:{limit}"
            data, attempts = gateway.fetch_ohlcv(fetch_symbol, timeframe, limit=limit, max_retries=max_retries)
            if data and self.cache_service is not None:
                self.cache_service.set(cache_key, data, ttl=settings.REDIS_KLINE_TTL)
            return data
        except Exception as e:
            logger.error(f"实时K线获取错误 (Exchange): {e}")
            return []
        finally:
            elapsed = time.time() - start_time
            logger.debug(
                f"[metrics] get_live_kline_data symbol={symbol} tf={timeframe} limit={limit} "
                f"attempts={attempts} elapsed={elapsed:.2f}s"
            )

    def get_history_data(self, symbol: str, timeframe: str, end_ts: int, limit: int = 500) -> list[list[float]]:
        start_time = time.time()
        try:
            return self.kline_store.get_before(self.symbol_routing.storage_symbol(symbol), timeframe, end_ts, limit)
        except Exception as e:
            logger.error(f"历史数据查询失败: {e}")
            raise
        finally:
            elapsed = time.time() - start_time
            logger.debug(f"[metrics] get_history_data symbol={symbol} tf={timeframe} limit={limit} elapsed={elapsed:.2f}s")

    def get_recent_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = settings.LIMIT,
        *,
        allow_cached_response: bool = False,
        live_max_retries: int | None = None,
    ) -> list[list[float]]:
        end_ts = int(time.time() * 1000)
        timeframe_ms = timeframe_to_milliseconds(timeframe)
        storage_symbol = self.symbol_routing.storage_symbol(symbol)
        start_time = time.time()
        try:
            if timeframe_ms > 0:
                start_ts = end_ts - (timeframe_ms * max(limit, 1))
                cached = self.kline_store.get_range(storage_symbol, timeframe, start_ts, end_ts)
            else:
                cached = self.get_history_data(symbol, timeframe, end_ts, limit)
        except Exception as exc:
            logger.warning(f"最近 K 线缓存读取失败，改用交易所实时数据: {exc}")
            cached = []

        if allow_cached_response and is_recent_cache_usable(
            cached=cached,
            timeframe=timeframe,
            limit=limit,
            now_ms=end_ts,
        ):
            return cached[-limit:]

        retry_limit = live_max_retries if live_max_retries is not None else settings.EXCHANGE_TAIL_MAX_RETRIES
        live_rows = self.get_live_kline_data(symbol, timeframe, limit=limit, max_retries=retry_limit)
        if live_rows:
            merged = merge_ohlcv_rows(cached, live_rows)
            try:
                self.kline_store.save(storage_symbol, timeframe, live_rows)
            except Exception as exc:
                logger.warning(f"最近 K 线回写缓存失败: {exc}")
            logger.debug(
                f"[metrics] get_recent_candles symbol={symbol} tf={timeframe} limit={limit} "
                f"cached={len(cached)} live={len(live_rows)} elapsed={time.time() - start_time:.2f}s"
            )
            return merged[-limit:]
        logger.debug(
            f"[metrics] get_recent_candles symbol={symbol} tf={timeframe} limit={limit} "
            f"cached={len(cached)} live=0 elapsed={time.time() - start_time:.2f}s"
        )
        return cached[-limit:]

    def load_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        persist_klines: Callable[[str, str, list[list[float]]], None] | None = None,
    ) -> OhlcvRangeResult:
        start_ts = int(start_date.timestamp() * 1000)
        end_ts_exclusive = int(end_date.timestamp() * 1000) + 1

        def persist(storage_symbol: str, current_timeframe: str, rows: list[list[float]]) -> None:
            try:
                (persist_klines or self.kline_store.save)(storage_symbol, current_timeframe, rows)
            except Exception as exc:
                logger.warning(f"历史 K 线回写缓存失败: {exc}")

        return self.history_ranges.load(
            storage_symbol=self.symbol_routing.storage_symbol(symbol),
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
            fetch_gap=lambda since, until: self.exchange_history.fetch_gap(symbol, timeframe, since, until),
            persist=persist,
            fallback_on_cache_error=True,
        )

    def load_cached_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> OhlcvRangeResult:
        start_ts = int(start_date.timestamp() * 1000)
        end_ts_exclusive = int(end_date.timestamp() * 1000) + 1
        return self.history_ranges.read_cached(
            storage_symbol=self.symbol_routing.storage_symbol(symbol),
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
        )

    def load_live_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> OhlcvRangeResult:
        start_ts = int(start_date.timestamp() * 1000)
        end_ts_exclusive = int(end_date.timestamp() * 1000) + 1
        rows = self.exchange_history.fetch_gap(symbol, timeframe, start_ts, end_ts_exclusive)
        return self.history_ranges.from_live_rows(
            rows=rows,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
        )

    def save_klines_background(self, symbol: str, timeframe: str, klines: list[list[float]]) -> None:
        try:
            self.kline_store.save(symbol, timeframe, klines)
            logger.info(f"[Background] Saved {len(klines)} klines for {symbol}")
        except Exception as e:
            logger.error(f"[Background] Save failed: {e}")
