from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from app.application.errors import InvalidRequestError
from app.contracts.dto.market_history import CurrentPriceBatchItemResponse, CurrentPriceBatchResponse, CurrentPriceResponse
from app.contracts.market_history import (
    build_current_price_batch_response,
)
from app.infra.executor import run_database
from app.domain.market.quotes import MarketQuote
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
        return CurrentPriceResponse(**await self._quote_payload(symbol, timeframe))

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
        return CurrentPriceBatchItemResponse(**await self._quote_payload(symbol, timeframe))

    async def _quote_payload(self, symbol, timeframe):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        quote = await self.binance_snapshot_service.get_current_quote(symbol) if self.binance_snapshot_service is not None else MarketQuote()
        if not quote.fresh(now_ms, settings.MARKET_QUOTE_MAX_AGE_SECONDS):
            # A long-period bar says nothing about when its current close was
            # observed. Only completed minute bars can bound a cached quote age.
            rows = await run_database(lambda: self.market_data_service.get_history_data(symbol, "1m", now_ms, 2))
            closed = [row for row in rows if int(row[0]) + 60_000 <= now_ms]
            cached = MarketQuote(float(closed[-1][4]), int(closed[-1][0]) + 60_000, None, "cached_history") if closed else MarketQuote()
            if cached.observed_at is not None and (quote.value is None or quote.observed_at is None or cached.observed_at > quote.observed_at):
                quote = cached
        fresh = quote.fresh(now_ms, settings.MARKET_QUOTE_MAX_AGE_SECONDS)
        def iso(value):
            return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat() if value is not None else None
        return dict(symbol=symbol,timeframe=timeframe,timestamp=iso(quote.observed_at),
                    current_price=quote.value if fresh else None,source=quote.source,
                    received_at=iso(quote.received_at),queried_at=iso(now_ms),
                    valid_until=iso(quote.observed_at + int(settings.MARKET_QUOTE_MAX_AGE_SECONDS * 1000)) if quote.observed_at else None,
                    status="fresh" if fresh else "stale" if quote.observed_at else "unavailable",market=quote.market)
