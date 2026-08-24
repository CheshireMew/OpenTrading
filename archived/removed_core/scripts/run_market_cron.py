from __future__ import annotations

import asyncio

from app.application.indicators.market_cron import MarketIndicatorCronJob
from app.infra.db.database import build_database_runtime
from app.infra.db.schema_runtime import init_db
from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
from app.services.market_scheduler_runtime import _build_indicator_providers
from config import settings


def main() -> None:
    runtime = build_database_runtime(settings)
    try:
        init_db(runtime)
        asyncio.run(
            MarketIndicatorCronJob(
                repository=MarketIndicatorRepository(database_runtime=runtime),
                providers=_build_indicator_providers(),
            ).run()
        )
    finally:
        runtime.dispose()


if __name__ == "__main__":
    main()
