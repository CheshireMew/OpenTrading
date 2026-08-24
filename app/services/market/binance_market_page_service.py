from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.contracts.dto.binance.page import (
    BinanceBreakoutMonitorResponse,
    BinanceMarketPageResponse,
)
from app.contracts.dto.market_history import MarketHistoryResponse
from app.infra.executor import run_compute
from config import settings
from utils.logger import logger

from .binance_breakout_monitor import BinanceBreakoutMonitor
from .binance_contract_oi_enricher import BinanceContractOpenInterestEnricher
from .binance_market_board_builder import BinanceMarketBoardBuilder
from .binance_market_page_state import BinanceMarketPageState, PageKey
from .binance_spot_market import BinanceSpotMarketService
from .binance_usdm_market import BinanceUsdmMarketService

if TYPE_CHECKING:
    from .binance_market_snapshot_service import BinanceMarketSnapshotService


class BinanceMarketPageService:
    def __init__(
        self,
        *,
        spot: BinanceSpotMarketService,
        usdm: BinanceUsdmMarketService,
        snapshot_service: BinanceMarketSnapshotService,
    ) -> None:
        self.spot = spot
        self.usdm = usdm
        self.snapshot_service = snapshot_service
        self.breakout_monitor = BinanceBreakoutMonitor(self._get_market_klines)
        self.board_builder = BinanceMarketBoardBuilder()
        self.oi_enricher = BinanceContractOpenInterestEnricher(usdm)
        self.state = BinanceMarketPageState()
        self._refresh_event: asyncio.Event | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._refresh_event = asyncio.Event()
        self._refresh_task = asyncio.create_task(self._run_refresh_loop(), name="binance-market-page-refresh")

    async def shutdown(self) -> None:
        self._running = False
        if self._refresh_event is not None:
            self._refresh_event.set()
        task = self._refresh_task
        self._refresh_task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def get_page(
        self,
        *,
        min_rise_pct: float = 5.0,
        limit: int = 24,
        quote_asset: str = "USDT",
    ) -> BinanceMarketPageResponse:
        key = self.state.key(min_rise_pct=min_rise_pct, limit=limit, quote_asset=quote_asset)
        cached_response, should_notify_refresh = await self.state.register_request(key)
        if cached_response is not None:
            return cached_response

        if should_notify_refresh:
            self._request_refresh()
        return await self._build_pending_page(key)

    async def refresh_requested_payloads(self) -> None:
        keys = await self.state.requested_keys()
        if not keys:
            return

        await self.state.mark_started()
        try:
            market_snapshot = await self._load_market_page_snapshot_for_refresh()
            ticker_rows = [item for item in market_snapshot["usdm_ticker"].get("items", [])]
            oi_changes = await self.oi_enricher.load_changes(ticker_rows)
            grouped: dict[str, list[PageKey]] = {}
            for key in keys:
                grouped.setdefault(key[2], []).append(key)

            for quote_asset, quote_keys in grouped.items():
                try:
                    board_fields = await run_compute(
                        lambda quote_asset=quote_asset: self.board_builder.build_response_fields(
                            market_snapshot,
                            quote_asset=quote_asset,
                            oi_changes=oi_changes,
                        )
                    )
                    base_monitor = await self.breakout_monitor.build(
                        market_snapshot=market_snapshot,
                        min_rise_pct=min(key[0] for key in quote_keys),
                        limit=max(key[1] for key in quote_keys),
                        quote_asset=quote_asset,
                    )
                    for key in quote_keys:
                        min_rise_pct, limit, _ = key
                        monitor = self.breakout_monitor.derive(
                            base_monitor,
                            min_rise_pct=min_rise_pct,
                            limit=limit,
                        )
                        response = BinanceMarketPageResponse.model_validate({
                            "exchange": "binance",
                            "quote_asset": quote_asset,
                            "updated_at": max(
                                int(monitor.get("updated_at") or 0),
                                int(market_snapshot["updated_at"] or 0),
                            ),
                            "monitor": monitor,
                            **board_fields,
                            "refresh_status": self.state.build_status(
                                snapshot_ready=not board_fields["load_errors"],
                                boards_ready=True,
                                monitor_ready=True,
                                oi_ready_count=sum(1 for summary in oi_changes.values() if summary),
                                oi_requested_count=len(self.oi_enricher.candidate_symbols(ticker_rows)),
                            ),
                        })
                        await self.state.store(key, response)
                except Exception as exc:
                    await self.state.mark_failed(exc)
                    logger.warning("Binance market page refresh failed for %s: %s", quote_asset, exc)
        except Exception as exc:
            await self.state.mark_failed(exc)
            logger.warning("Binance market page refresh failed: %s", exc)
        finally:
            await self.state.mark_completed()

    async def refresh_page(self, key: PageKey) -> BinanceMarketPageResponse:
        min_rise_pct, limit, quote_asset = key
        await self.state.mark_started()
        try:
            market_snapshot = await self._load_market_page_snapshot_for_refresh()
            ticker_rows = [item for item in market_snapshot["usdm_ticker"].get("items", [])]
            oi_changes = await self.oi_enricher.load_changes(ticker_rows)
            board_fields = await run_compute(
                lambda: self.board_builder.build_response_fields(
                    market_snapshot,
                    quote_asset=quote_asset,
                    oi_changes=oi_changes,
                )
            )
            monitor = await self.breakout_monitor.build(
                market_snapshot=market_snapshot,
                min_rise_pct=min_rise_pct,
                limit=limit,
                quote_asset=quote_asset,
            )
            response = BinanceMarketPageResponse.model_validate({
                "exchange": "binance",
                "quote_asset": quote_asset,
                "updated_at": max(int(monitor.get("updated_at") or 0), int(market_snapshot["updated_at"] or 0)),
                "monitor": monitor,
                **board_fields,
                "refresh_status": self.state.build_status(
                    snapshot_ready=not board_fields["load_errors"],
                    boards_ready=True,
                    monitor_ready=True,
                    oi_ready_count=sum(1 for summary in oi_changes.values() if summary),
                    oi_requested_count=len(self.oi_enricher.candidate_symbols(ticker_rows)),
                ),
            })
            await self.state.store(key, response)
            return response
        finally:
            await self.state.mark_completed()

    async def _run_refresh_loop(self) -> None:
        while self._running:
            await self.refresh_requested_payloads()
            event = self._refresh_event
            if event is None:
                return
            try:
                await asyncio.wait_for(event.wait(), timeout=max(float(settings.BINANCE_MARKET_PAGE_REFRESH_INTERVAL), 1.0))
            except asyncio.TimeoutError:
                pass
            event.clear()

    async def _load_market_page_snapshot_for_refresh(self) -> dict[str, Any]:
        if not await self.snapshot_service.has_market_page_snapshot():
            await self.snapshot_service.seed(
                spot_ticker_loader=self.spot.get_ticker_24hr,
                usdm_ticker_loader=self.usdm.get_ticker_24hr,
                usdm_mark_loader=self.usdm.get_mark_price,
            )
        return await self.snapshot_service.get_market_page_snapshot_data()

    async def _get_market_klines(self, market: str, symbol: str, interval: str, limit: int) -> dict[str, Any]:
        if market == "spot":
            response = await self.spot.get_klines(symbol=symbol, interval=interval, limit=limit)
        else:
            response = await self.usdm.get_klines(symbol=symbol, interval=interval, limit=limit)
        return response.model_dump() if hasattr(response, "model_dump") else response

    async def get_chart_klines(
        self,
        *,
        market: str,
        symbol: str,
        interval: str,
        limit: int,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> MarketHistoryResponse:
        loader = self.spot if market == "spot" else self.usdm
        response = await loader.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )
        raw = response.model_dump() if hasattr(response, "model_dump") else response
        return MarketHistoryResponse.model_validate({
            "symbol": str(raw.get("symbol") or symbol).upper(),
            "timeframe": interval,
            "items": [
                {
                    "timestamp": item.get("open_time"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "volume": item.get("volume"),
                }
                for item in raw.get("items", [])
            ],
        })

    async def _build_pending_page(self, key: PageKey) -> BinanceMarketPageResponse:
        min_rise_pct, limit, quote_asset = key
        market_snapshot = await self.snapshot_service.get_market_page_snapshot_data()
        board_fields = await run_compute(
            lambda: self.board_builder.build_response_fields(
                market_snapshot,
                quote_asset=quote_asset,
                oi_changes={},
            )
        )
        return BinanceMarketPageResponse.model_validate({
            "exchange": "binance",
            "quote_asset": quote_asset,
            "updated_at": int(market_snapshot["updated_at"] or 0),
            "monitor": self._empty_monitor(
                min_rise_pct=min_rise_pct,
                limit=limit,
                quote_asset=quote_asset,
                updated_at=int(market_snapshot["updated_at"] or 0),
            ),
            **board_fields,
            "refresh_status": self.state.build_status(
                snapshot_ready=not board_fields["load_errors"],
                boards_ready=True,
                monitor_ready=False,
                oi_ready_count=0,
                oi_requested_count=len(self.oi_enricher.candidate_symbols(market_snapshot["usdm_ticker"].get("items", []))),
            ),
        })

    def _empty_monitor(self, *, min_rise_pct: float, limit: int, quote_asset: str, updated_at: int) -> BinanceBreakoutMonitorResponse:
        return BinanceBreakoutMonitorResponse(
            exchange="binance",
            min_rise_pct=min_rise_pct,
            quote_asset=quote_asset,
            updated_at=updated_at,
            items=[],
        )

    def _request_refresh(self) -> None:
        if self._refresh_event is not None:
            self._refresh_event.set()
