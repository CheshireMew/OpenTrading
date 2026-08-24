from __future__ import annotations

from typing import Any, Callable, Literal

from app.contracts.dto.market_history import (
    CurrentPriceBatchResponse,
    CurrentPriceResponse,
    KlineTailResponse,
    MarketHistoryBatchResponse,
    MarketHistoryResponse,
    RealtimeResponse,
)
from app.services.market.app_service_support import VALID_MARKET_SYMBOLS, VALID_MARKET_TIMEFRAMES
from app.services.market.history_query_service import MarketHistoryQueryService
from app.services.market.market_data_service import MarketDataService
from app.services.market.price_query_service import MarketPriceQueryService
from app.services.market.realtime_query_service import MarketRealtimeQueryService
from app.services.market.realtime_service import MarketSnapshot, RealtimeService


class MarketQueryAppService:
    def __init__(
        self,
        *,
        market_data_service: MarketDataService,
        realtime_service: RealtimeService,
        binance_snapshot_service=None,
        llm_client_factory: Callable[[], Any | None] | None = None,
    ) -> None:
        self.realtime = MarketRealtimeQueryService(
            market_data_service=market_data_service,
            realtime_service=realtime_service,
            llm_client_factory=llm_client_factory,
        )
        self.history = MarketHistoryQueryService(market_data_service=market_data_service)
        self.prices = MarketPriceQueryService(
            market_data_service=market_data_service,
            binance_snapshot_service=binance_snapshot_service,
        )
        self.valid_symbols = list(VALID_MARKET_SYMBOLS)
        self.valid_timeframes = list(VALID_MARKET_TIMEFRAMES)

    async def load_snapshot(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> MarketSnapshot:
        return await self.realtime.load_snapshot(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

    async def get_realtime(
        self,
        *,
        symbol: str,
        timeframe: str | None,
        limit: int | None,
    ) -> RealtimeResponse:
        return await self.realtime.get_realtime(symbol=symbol, timeframe=timeframe, limit=limit)

    async def get_realtime_ws_payload(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        use_ai: bool,
    ) -> RealtimeResponse:
        return await self.realtime.get_realtime_ws_payload(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            use_ai=use_ai,
        )

    async def get_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        end_ts: int,
        limit: int,
    ) -> MarketHistoryResponse:
        return await self.history.get_history(symbol=symbol, timeframe=timeframe, end_ts=end_ts, limit=limit)

    async def get_recent_klines(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> MarketHistoryResponse:
        return await self.history.get_recent_klines(symbol=symbol, timeframe=timeframe, limit=limit)

    async def get_live_kline_tail(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> KlineTailResponse:
        return await self.history.get_live_kline_tail(symbol=symbol, timeframe=timeframe, limit=limit)

    async def get_current_price(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> CurrentPriceResponse:
        return await self.prices.get_current_price(symbol=symbol, timeframe=timeframe)

    async def get_current_price_batch(
        self,
        *,
        symbols: list[str],
        timeframe: str,
    ) -> CurrentPriceBatchResponse:
        return await self.prices.get_current_price_batch(symbols=symbols, timeframe=timeframe)

    async def get_full_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        fetch_policy: Literal["cache_only", "hydrate"] = "hydrate",
        persist_klines: Callable[[str, str, list[list[float]]], None] | None = None,
    ) -> MarketHistoryResponse:
        return await self.history.get_full_history(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            fetch_policy=fetch_policy,
            persist_klines=persist_klines,
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
        return await self.history.get_full_history_batch(
            symbols=symbols,
            timeframe=timeframe,
            start_date=start_date,
            fetch_policy=fetch_policy,
            persist_klines=persist_klines,
        )
