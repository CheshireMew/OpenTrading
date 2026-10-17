from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.application.indicators.market_cron import MarketIndicatorCronJob
from app.infra.executor import run_background, run_database
from app.application.persistence_ports import DataRetentionCleanup, IndicatorRepositoryPort
from config import settings
from app.infra.persistence.runtime_status_repository import (
    BACKGROUND_COMPONENT,
    MARKET_INDICATORS_COMPONENT,
    RuntimeStatusRepository,
)

logger = logging.getLogger(__name__)


class MarketSchedulerRuntime:
    def __init__(
        self,
        *,
        indicator_repository: IndicatorRepositoryPort,
        cleanup_old_data: DataRetentionCleanup,
        runtime_status_repository: RuntimeStatusRepository | None = None,
    ) -> None:
        self._cleanup_old_data_callback = cleanup_old_data
        self.scheduler = AsyncIOScheduler()
        self._runtime_status = runtime_status_repository
        self._owner_id = ""
        self._indicator_lock = asyncio.Lock()
        self._bootstrap_task: asyncio.Task[None] | None = None
        self._job = MarketIndicatorCronJob(
            repository=indicator_repository,
            providers=_build_indicator_providers(),
        )

    async def start(self, owner_id: str = "") -> None:
        if self.scheduler.running:
            logger.info("Market Indicator Scheduler already running, skip duplicate start.")
            if self._bootstrap_task is not None:
                await self._bootstrap_task
            return

        self._owner_id = owner_id
        self.scheduler.add_job(
            self._run_market_indicator_job,
            'interval',
            hours=settings.MARKET_CRON_INTERVAL_HOURS,
            id='fetch_market_indicators',
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

        self.scheduler.add_job(
            self._cleanup_old_data,
            'interval',
            hours=24,
            id='data_retention_cleanup',
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

        if self._runtime_status is not None and owner_id:
            self.scheduler.add_job(
                self._heartbeat,
                'interval',
                seconds=settings.BACKGROUND_HEARTBEAT_INTERVAL_SECONDS,
                id='background_heartbeat',
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )

        self.scheduler.start()
        self._bootstrap_task = asyncio.create_task(
            self._run_first_collection(),
            name="market-indicators-first-collection",
        )
        await self._bootstrap_task
        logger.info(f"Market Indicator Scheduler Started. Fetching every {settings.MARKET_CRON_INTERVAL_HOURS} hours.")

    async def _run_market_indicator_job(self) -> None:
        async with self._indicator_lock:
            next_run_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                hours=settings.MARKET_CRON_INTERVAL_HOURS
            )
            if self._runtime_status is not None and self._owner_id:
                await run_background(
                    lambda: self._runtime_status.mark_running(
                        MARKET_INDICATORS_COMPONENT,
                        self._owner_id,
                        next_run_at=next_run_at,
                    )
                )
            try:
                data_points = await self._job.collect()
                await run_database(lambda: self._job.persist(data_points))
            except Exception as exc:
                error_detail = str(exc)
                if self._runtime_status is not None and self._owner_id:
                    await run_background(
                        lambda: self._runtime_status.mark_failed(
                            MARKET_INDICATORS_COMPONENT,
                            self._owner_id,
                            error_code="collection_failed",
                            error_detail=error_detail,
                            next_run_at=next_run_at,
                        )
                    )
                raise
            if self._runtime_status is not None and self._owner_id:
                await run_background(
                    lambda: self._runtime_status.mark_success(
                        MARKET_INDICATORS_COMPONENT,
                        self._owner_id,
                        next_run_at=next_run_at,
                    )
                )

    async def _heartbeat(self) -> None:
        if self._runtime_status is not None and self._owner_id:
            await run_background(
                lambda: self._runtime_status.heartbeat(BACKGROUND_COMPONENT, self._owner_id)
            )

    async def _run_first_collection(self) -> None:
        try:
            await self._run_market_indicator_job()
        except Exception:
            logger.exception("Initial market indicator collection failed.")
            raise

    async def _cleanup_old_data(self) -> None:
        await run_background(self._cleanup_old_data_callback)

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if self._bootstrap_task is not None:
            if not self._bootstrap_task.done():
                self._bootstrap_task.cancel()
            await asyncio.gather(self._bootstrap_task, return_exceptions=True)
            self._bootstrap_task = None


def _build_indicator_providers():
    from app.services.indicators.onchain_provider import OnchainProvider
    from app.services.indicators.sentiment_provider import SentimentProvider
    from app.services.indicators.tech_calculator import TechCalculatorProvider

    return [
        OnchainProvider(),
        SentimentProvider(),
        TechCalculatorProvider(),
    ]
