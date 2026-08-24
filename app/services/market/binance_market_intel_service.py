from __future__ import annotations

import asyncio

from config import settings
from app.application.persistence_ports import CacheServicePort, BinanceMarketResearchStorePort

from .binance_api_support import BinanceApiSupport
from .binance_market_page_service import BinanceMarketPageService
from .binance_market_snapshot_service import BinanceMarketSnapshotService
from .binance_spot_market import BinanceSpotMarketService
from .binance_usdm_market import BinanceUsdmMarketService

class BinanceMarketIntelService:
    def __init__(
        self,
        *,
        research_store: BinanceMarketResearchStorePort,
        snapshot_service: BinanceMarketSnapshotService | None = None,
        cache_service: CacheServicePort | None = None,
    ) -> None:
        spot_client = BinanceApiSupport(
            base_url=settings.BINANCE_PUBLIC_BASE_URL,
            cache_namespace="binance:spot",
            user_agent="heimdall/market-intel",
            cache_service=cache_service,
        )
        usdm_client = BinanceApiSupport(
            base_url=settings.BINANCE_FUTURES_USDM_BASE_URL,
            cache_namespace="binance:usdm",
            user_agent="heimdall/market-intel",
            cache_service=cache_service,
        )
        self.spot = BinanceSpotMarketService(spot_client, research_store=research_store)
        self.usdm = BinanceUsdmMarketService(
            usdm_client,
            research_store=research_store,
        )
        self.snapshot_service = snapshot_service or BinanceMarketSnapshotService(
            spot_ticker_loader=self.spot.get_ticker_24hr,
            usdm_ticker_loader=self.usdm.get_ticker_24hr,
            usdm_mark_loader=self.usdm.get_mark_price,
        )
        self.page = BinanceMarketPageService(
            spot=self.spot,
            usdm=self.usdm,
            snapshot_service=self.snapshot_service,
        )

    async def start(self) -> None:
        await self.snapshot_service.start()
        self.page.start()

    async def shutdown(self) -> None:
        await asyncio.gather(
            self.page.shutdown(),
            self.snapshot_service.shutdown(),
            self.spot.client.aclose(),
            self.usdm.client.aclose(),
            return_exceptions=True,
        )
