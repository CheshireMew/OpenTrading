from __future__ import annotations

from dataclasses import replace
from functools import cached_property
from pathlib import Path

from app.infra.db.database import DatabaseRuntime
from config.settings import AppSettings
from config.market_data import MarketDataConfig
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.services.market.history.views import MarketDataViews


class MarketDataRuntime:
    def __init__(self, database: DatabaseRuntime, settings: AppSettings, *, root: Path | None = None) -> None:
        self.database_runtime, self.settings = database, settings
        self.engine = database.engine
        self.config = MarketDataConfig.from_settings(settings)
        self.config = replace(self.config, data_dir=self.config.resolve_data_dir(root))
        self.database = MarketHistoryDatabase(self.config.data_dir, engine=database.engine)
        self.watcher = None
        self.views = MarketDataViews.create(self.config, self.database)

    @cached_property
    def prices(self):
        from app.services.market.history.prices import PriceService
        return PriceService(self.database, self.config)

    @cached_property
    def classifications(self):
        from app.services.market.history.classifications import ClassificationService
        return ClassificationService(self.database, self.config)

    @cached_property
    def indicators(self):
        from app.services.market.history.indicators import PriceIndicatorService
        return PriceIndicatorService(self.database, self.config)

    @cached_property
    def datasets(self):
        from app.services.market.history.datasets import PriceDatasetService
        return PriceDatasetService(self.database, self.config, prices=self.prices,
                                   indicators=self.indicators, classifications=self.classifications)

    @cached_property
    def macro(self):
        from app.services.market.history.macro import MacroService
        return MacroService(self.database, self.config)

    @cached_property
    def bundles(self):
        from app.infra.persistence.market.history.bundles import SnapshotBundleService
        return SnapshotBundleService(self.database, self.config)

    @cached_property
    def scheduler(self):
        from app.services.market.history_jobs import JobScheduler
        return JobScheduler(self.config, self.database)

    def start(self) -> None:
        from app.services.market.history_jobs import LIQUIDITY_REFRESH_JOB, JobWatcher

        self.scheduler.ensure_preset(LIQUIDITY_REFRESH_JOB)
        self.watcher = JobWatcher(self.scheduler)
        self.watcher.start()

    def shutdown(self) -> None:
        if self.watcher is not None:
            self.watcher.stop(timeout=None)
            self.watcher = None
