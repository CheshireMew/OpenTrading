import asyncio
import logging

from app.application.indicators.ports import IndicatorProvider, MarketIndicatorWriter
from app.domain.market.indicator_catalog import market_indicator_meta_catalog

logger = logging.getLogger(__name__)

class MarketIndicatorCronJob:
    """市场核心指标定时汇聚作业类"""

    def __init__(
        self,
        *,
        repository: MarketIndicatorWriter,
        providers: list[IndicatorProvider],
    ):
        self.repository = repository
        self.providers = providers

    async def collect(self) -> list:
        """Collect all provider results and fail when no provider completed."""
        logger.info("Starting MarketIndicator Cron Job...")

        results = await asyncio.gather(
            *(provider.fetch_data() for provider in self.providers),
            return_exceptions=True,
        )
        all_data_points = []
        completed_provider_count = 0
        for provider, points in zip(self.providers, results):
            if isinstance(points, Exception):
                logger.error(
                    "Error fetching from provider %s: %s",
                    provider.__class__.__name__,
                    points,
                )
                continue
            completed_provider_count += 1
            all_data_points.extend(points)

        if completed_provider_count == 0:
            raise RuntimeError("All market indicator providers failed")

        return all_data_points

    def persist(self, data_points: list) -> None:
        if data_points:
            self.repository.upsert_points(data_points, market_indicator_meta_catalog())

    async def run(self):
        """Compatibility entry point for callers that own a blocking context."""
        all_data_points = await self.collect()
        self.persist(all_data_points)

        logger.info(f"MarketIndicator Cron Job Complete. Inserted {len(all_data_points)} records.")
        return len(all_data_points)

