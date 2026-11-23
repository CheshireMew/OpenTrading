from __future__ import annotations

from app.infra.db.database import DatabaseRuntime
from config.settings import AppSettings
from config.market_data import MarketDataConfig
from app.infra.persistence.market.history.database import bind_database
from app.services.market.history.views import MarketDataViews


class MarketDataRuntime:
    def __init__(self, database: DatabaseRuntime, settings: AppSettings) -> None:
        self.engine = database.engine
        self.config = MarketDataConfig.from_settings(settings)
        self.watcher = None
        with self.bind():
            self.views = MarketDataViews.create(self.config, self.config.data_dir)

    def bind(self):
        return bind_database(self.engine, self.config.data_dir)

    def start(self) -> None:
        from app.services.market.history_jobs import LIQUIDITY_REFRESH_JOB, JobScheduler, JobWatcher

        with self.bind():
            scheduler = JobScheduler(self.config, self.config.data_dir)
            scheduler.ensure_preset(LIQUIDITY_REFRESH_JOB)
            self.watcher = JobWatcher(scheduler)
            self.watcher.start()

    def shutdown(self) -> None:
        if self.watcher is not None:
            self.watcher.stop(timeout=None)
            self.watcher = None
