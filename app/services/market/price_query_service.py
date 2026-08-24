from __future__ import annotations

import asyncio
from datetime import datetime
from app.application.errors import InvalidRequestError
from app.contracts.dto.market_history import CurrentPriceBatchItemResponse, CurrentPriceBatchResponse, CurrentPriceResponse
from app.contracts.market_history import (
    build_current_price_batch_item_response,
    build_current_price_batch_response,
    build_current_price_response,
)
from app.infra.executor import run_database
from app.services.market.app_service_support import validate_market_request
from app.services.market.market_data_service import MarketDataService
from config import settings


class MarketPriceQueryService:
    def __init__(
        self,
        *,
        market_data_service: MarketDataService,
        binance_snapshot_service=None,
    ) -> None:
        self.market_data_service = market_data_service
        self.binance_snapshot_service = binance_snapshot_service

    async def get_current_price(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> CurrentPriceResponse:
        validate_market_request(symbol, timeframe)
        current_price = await self._get_current_price_from_snapshot(symbol)
        if current_price is None:
            current_price = await self._get_current_price_from_cached_history(
                symbol=symbol,
                timeframe=timeframe,
            )
        return build_current_price_response(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now().isoformat(),
            current_price=current_price,
        )

    async def get_current_price_batch(
        self,
        *,
        symbols: list[str],
        timeframe: str,
    ) -> CurrentPriceBatchResponse:
        normalized_symbols: list[str] = []
        seen_symbols: set[str] = set()
        for symbol in symbols:
            validate_market_request(symbol, timeframe)
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            normalized_symbols.append(symbol)

        if len(normalized_symbols) > settings.PRICE_BATCH_MAX_SYMBOLS:
            raise InvalidRequestError(
                f"批量价格一次最多查询 {settings.PRICE_BATCH_MAX_SYMBOLS} 个标的"
            )

        semaphore = asyncio.Semaphore(max(int(settings.PRICE_BATCH_CONCURRENCY), 1))

        async def load_one(symbol: str):
            async with semaphore:
                return await self._build_current_price_batch_item(
                    symbol=symbol,
                    timeframe=timeframe,
                )

        items = await asyncio.gather(
            *(load_one(symbol) for symbol in normalized_symbols),
        )
        return build_current_price_batch_response(timeframe=timeframe, items=items)

    async def _build_current_price_batch_item(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> CurrentPriceBatchItemResponse:
        current_price = await self._get_current_price_from_snapshot(symbol)
        source = "websocket_snapshot" if current_price is not None else "cached_history"
        if current_price is None:
            current_price = await self._get_current_price_from_cached_history(
                symbol=symbol,
                timeframe=timeframe,
            )
        return build_current_price_batch_item_response(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now().isoformat(),
            current_price=current_price,
            source=source if current_price is not None else "unavailable",
        )

    async def _get_current_price_from_snapshot(self, symbol: str) -> float | None:
        if self.binance_snapshot_service is None:
            return None
        return await self.binance_snapshot_service.get_current_price(symbol)

    async def _get_current_price_from_cached_history(
        self,
        *,
        symbol: str,
        timeframe: str,
    ) -> float | None:
        end_ts = int(datetime.now().timestamp() * 1000)
        kline_data = await run_database(
            lambda: self.market_data_service.get_history_data(
                symbol,
                timeframe,
                end_ts,
                1,
            )
        )
        return kline_data[-1][4] if kline_data else None
