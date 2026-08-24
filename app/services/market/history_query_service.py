from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Literal

from app.application.errors import InvalidRequestError

from app.contracts.market_history import (
    build_kline_tail_response,
    build_market_history_batch_response,
    build_market_history_response,
)
from app.contracts.dto.market_history import KlineTailResponse, MarketHistoryBatchResponse, MarketHistoryResponse
from app.infra.executor import run_database, run_external_io
from app.services.market.app_service_support import validate_market_request
from app.services.market.market_data_service import MarketDataService
from app.domain.market.constants import timeframe_to_milliseconds
from config import settings


class MarketHistoryQueryService:
    def __init__(self, *, market_data_service: MarketDataService) -> None:
        self.market_data_service = market_data_service

    async def get_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        end_ts: int,
        limit: int,
    ) -> MarketHistoryResponse:
        validate_market_request(symbol, timeframe)
        rows = await run_database(
            lambda: self.market_data_service.get_history_data(symbol, timeframe, end_ts, limit)
        )
        return build_market_history_response(symbol=symbol, timeframe=timeframe, rows=rows)

    async def get_recent_klines(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> MarketHistoryResponse:
        validate_market_request(symbol, timeframe)
        rows = await run_external_io(
            lambda: self.market_data_service.get_recent_candles(
                symbol,
                timeframe,
                limit,
                allow_cached_response=True,
            )
        )
        return build_market_history_response(symbol=symbol, timeframe=timeframe, rows=rows)

    async def get_live_kline_tail(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> KlineTailResponse:
        validate_market_request(symbol, timeframe)
        end_ts = int(datetime.now().timestamp() * 1000)
        kline_data = await run_database(
            lambda: self.market_data_service.get_history_data(
                symbol,
                timeframe,
                end_ts,
                limit,
            )
        )
        current_price = kline_data[-1][4] if kline_data else None
        return build_kline_tail_response(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now().isoformat(),
            current_price=current_price,
            rows=kline_data,
        )

    async def get_full_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        fetch_policy: Literal["cache_only", "hydrate"] = "hydrate",
        persist_klines: Callable[[str, str, list[list[float]]], None] | None = None,
    ) -> MarketHistoryResponse:
        validate_market_request(symbol, timeframe)
        rows, missing_ranges = await self._load_full_history_rows(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            fetch_policy=fetch_policy,
            persist_klines=persist_klines,
        )
        return build_market_history_response(
            symbol=symbol,
            timeframe=timeframe,
            rows=rows,
            missing_ranges=missing_ranges,
        )

    async def get_full_history_batch(
        self,
        *,
        symbols: list[str],
        timeframe: str,
        start_date: str,
        fetch_policy: Literal["cache_only", "hydrate"] = "hydrate",
        persist_klines: Callable[[str, str, list[list[float]]], None] | None = None,
    ) -> MarketHistoryBatchResponse:
        normalized_symbols: list[str] = []
        seen_symbols: set[str] = set()
        for symbol in symbols:
            validate_market_request(symbol, timeframe)
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            normalized_symbols.append(symbol)

        if len(normalized_symbols) > settings.HISTORY_BATCH_MAX_SYMBOLS:
            raise InvalidRequestError(
                f"批量历史数据一次最多查询 {settings.HISTORY_BATCH_MAX_SYMBOLS} 个标的"
            )

        semaphore = asyncio.Semaphore(max(int(settings.HISTORY_BATCH_CONCURRENCY), 1))

        async def load_one(symbol: str):
            async with semaphore:
                return await self._load_full_history_rows(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    fetch_policy=fetch_policy,
                    persist_klines=persist_klines,
                )

        series = await asyncio.gather(
            *(load_one(symbol) for symbol in normalized_symbols),
        )
        return build_market_history_batch_response(
            timeframe=timeframe,
            series_by_symbol=dict(zip(normalized_symbols, series, strict=False)),
        )

    async def _load_full_history_rows(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        fetch_policy: Literal["cache_only", "hydrate"],
        persist_klines: Callable[[str, str, list[list[float]]], None] | None,
    ) -> tuple[list[list[float]], list[tuple[int, int]]]:
        return await run_external_io(
            lambda: self._load_full_history_rows_sync(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                fetch_policy=fetch_policy,
                persist_klines=persist_klines,
            )
        )

    def _load_full_history_rows_sync(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        fetch_policy: Literal["cache_only", "hydrate"],
        persist_klines: Callable[[str, str, list[list[float]]], None] | None,
    ) -> tuple[list[list[float]], list[tuple[int, int]]]:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError as exc:
            raise InvalidRequestError("start_date 必须是 YYYY-MM-DD") from exc

        end_dt = datetime.now()
        interval_ms = timeframe_to_milliseconds(timeframe)
        if interval_ms > 0:
            estimated_points = int(
                max((end_dt - start_dt).total_seconds() * 1000, 0) / interval_ms
            ) + 1
            if estimated_points > settings.FULL_HISTORY_MAX_POINTS:
                raise InvalidRequestError(
                    "历史范围过大：当前周期最多返回 "
                    f"{settings.FULL_HISTORY_MAX_POINTS} 个数据点，请缩短日期范围或使用更大周期"
                )
        if fetch_policy == "cache_only":
            result = self.market_data_service.load_cached_ohlcv_range(
                symbol,
                timeframe,
                start_dt,
                end_dt,
            )
        else:
            result = self.market_data_service.load_ohlcv_range(
                symbol,
                timeframe,
                start_dt,
                end_dt,
                persist_klines=persist_klines,
            )
        return result.rows[-settings.FULL_HISTORY_MAX_POINTS :], result.missing_ranges
