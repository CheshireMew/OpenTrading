from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

from config import settings
from utils.logger import logger
from .binance_market_snapshot_store import BinanceMarketSnapshotStore
from .binance_market_stream_events import mark_from_event, ticker_from_event


TickerLoader = Callable[[], Awaitable[Any]]
MarkPriceLoader = Callable[[], Awaitable[Any]]


class BinanceMarketSnapshotService:
    def __init__(
        self,
        *,
        spot_ticker_loader: TickerLoader | None = None,
        usdm_ticker_loader: TickerLoader | None = None,
        usdm_mark_loader: MarkPriceLoader | None = None,
    ) -> None:
        self._store = BinanceMarketSnapshotStore()
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._seed_completed = False
        self._seed_success_count = 0
        self._seed_error: str | None = None
        self._seed_lock = asyncio.Lock()
        self._reconnect_delay = settings.BINANCE_MARKET_SNAPSHOT_RECONNECT_DELAY
        self._spot_ticker_loader = spot_ticker_loader
        self._usdm_ticker_loader = usdm_ticker_loader
        self._usdm_mark_loader = usdm_mark_loader

    async def start(
        self,
        *,
        spot_ticker_loader: TickerLoader | None = None,
        usdm_ticker_loader: TickerLoader | None = None,
        usdm_mark_loader: MarkPriceLoader | None = None,
    ) -> None:
        if self._running:
            return
        self._running = True
        self._seed_completed = False
        self._seed_success_count = 0
        self._seed_error = None
        self._tasks = [
            asyncio.create_task(
                self.seed(
                    spot_ticker_loader=spot_ticker_loader or self._spot_ticker_loader,
                    usdm_ticker_loader=usdm_ticker_loader or self._usdm_ticker_loader,
                    usdm_mark_loader=usdm_mark_loader or self._usdm_mark_loader,
                ),
                name="binance-market-snapshot-seed",
            ),
            asyncio.create_task(self._run_spot_ticker_loop(), name="binance-spot-ticker-snapshot"),
            asyncio.create_task(self._run_usdm_ticker_loop(), name="binance-usdm-ticker-snapshot"),
            asyncio.create_task(self._run_usdm_mark_loop(), name="binance-usdm-mark-snapshot"),
        ]

    async def shutdown(self) -> None:
        self._running = False
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks = []

    def health_snapshot(self) -> dict[str, Any]:
        if not self._running:
            status = "stopped"
        elif not self._seed_completed:
            status = "starting"
        elif self._seed_error is not None or self._seed_success_count == 0:
            status = "failed"
        else:
            status = "ready"
        return {
            "status": status,
            "seedCompleted": self._seed_completed,
            "seedSuccessCount": self._seed_success_count,
            "activeStreams": sum(1 for task in self._tasks[1:] if not task.done()),
            "error": self._seed_error,
        }

    async def seed(
        self,
        *,
        spot_ticker_loader: TickerLoader | None = None,
        usdm_ticker_loader: TickerLoader | None = None,
        usdm_mark_loader: MarkPriceLoader | None = None,
    ) -> None:
        async with self._seed_lock:
            self._seed_completed = False
            self._seed_success_count = 0
            self._seed_error = None
            try:
                if await self._store.has_market_page_snapshot():
                    self._seed_success_count = 1
                    return
                loaders = (
                    ("spot_ticker", spot_ticker_loader, self._apply_spot_ticker_response),
                    ("usdm_ticker", usdm_ticker_loader, self._apply_usdm_ticker_response),
                    ("usdm_mark", usdm_mark_loader, self._apply_usdm_mark_response),
                )
                results = await asyncio.gather(
                    *(loader() for _, loader, _ in loaders if loader is not None),
                    return_exceptions=True,
                )
                result_index = 0
                errors: list[str] = []
                for key, loader, applier in loaders:
                    if loader is None:
                        continue
                    result = results[result_index]
                    result_index += 1
                    if isinstance(result, Exception):
                        logger.warning("Binance snapshot seed failed: %s (%s)", key, result)
                        errors.append(f"{key}: {result}")
                        continue
                    await applier(result)
                    self._seed_success_count += 1
                if self._seed_success_count == 0:
                    self._seed_error = "; ".join(errors) or "No Binance snapshot loader completed"
            except Exception as exc:
                self._seed_error = str(exc)
                logger.exception("Binance snapshot seed failed unexpectedly")
            finally:
                self._seed_completed = True

    async def get_market_page_snapshot(self) -> dict[str, Any]:
        return await self._store.market_page_snapshot()

    async def get_market_page_snapshot_data(self) -> dict[str, Any]:
        return await self._store.market_page_snapshot_data()

    async def has_snapshot(self) -> bool:
        return await self._store.has_snapshot()

    async def has_market_page_snapshot(self) -> bool:
        return await self._store.has_market_page_snapshot()

    async def get_current_price(self, symbol: str) -> float | None:
        return await self._store.current_price(symbol)

    async def _apply_spot_ticker_response(self, response: Any) -> None:
        payload = response.model_dump() if hasattr(response, "model_dump") else response
        await self._store.merge_tickers("spot_ticker", payload.get("items", []))

    async def _apply_usdm_ticker_response(self, response: Any) -> None:
        payload = response.model_dump() if hasattr(response, "model_dump") else response
        await self._store.merge_tickers("usdm_ticker", payload.get("items", []))

    async def _apply_usdm_mark_response(self, response: Any) -> None:
        payload = response.model_dump() if hasattr(response, "model_dump") else response
        await self._store.merge_marks(payload.get("items", []))

    async def _run_spot_ticker_loop(self) -> None:
        await self._consume_json_array_stream(
            settings.BINANCE_SPOT_WS_URL,
            self._apply_spot_ticker_events,
            "spot ticker",
        )

    async def _run_usdm_ticker_loop(self) -> None:
        await self._consume_json_array_stream(
            settings.BINANCE_FUTURES_USDM_TICKER_WS_URL,
            self._apply_usdm_ticker_events,
            "usdm ticker",
        )

    async def _run_usdm_mark_loop(self) -> None:
        await self._consume_json_array_stream(
            settings.BINANCE_FUTURES_USDM_MARK_WS_URL,
            self._apply_usdm_mark_events,
            "usdm mark",
        )

    async def _consume_json_array_stream(
        self,
        url: str,
        handler: Callable[[list[dict[str, Any]]], Awaitable[None]],
        label: str,
    ) -> None:
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
                    logger.info("Binance snapshot WebSocket connected: %s", label)
                    async for message in websocket:
                        payload = json.loads(message)
                        events = payload if isinstance(payload, list) else [payload]
                        await handler([event for event in events if isinstance(event, dict)])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._running:
                    logger.warning("Binance snapshot WebSocket disconnected: %s (%s)", label, exc)
                    await asyncio.sleep(self._reconnect_delay)

    async def _apply_spot_ticker_events(self, events: list[dict[str, Any]]) -> None:
        await self._store.merge_tickers("spot_ticker", [ticker_from_event(event) for event in events])

    async def _apply_usdm_ticker_events(self, events: list[dict[str, Any]]) -> None:
        await self._store.merge_tickers("usdm_ticker", [ticker_from_event(event) for event in events])

    async def _apply_usdm_mark_events(self, events: list[dict[str, Any]]) -> None:
        await self._store.merge_marks([mark_from_event(event) for event in events])
