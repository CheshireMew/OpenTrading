from __future__ import annotations

from app.infra.db.database import DatabaseRuntime
from config.settings import BASE_DIR
from signal_lab.config import SignalLabConfig
from signal_lab.storage.database import bind_database
from signal_lab.web.service import WebServices


class SignalLabRuntime:
    def __init__(self, database: DatabaseRuntime) -> None:
        self.engine = database.engine
        self.config = SignalLabConfig.load(dotenv_path=BASE_DIR / ".env")
        self.watcher = None
        with self.bind():
            self.views = WebServices.create(self.config, self.config.data_dir)

    def bind(self):
        return bind_database(self.engine, self.config.data_dir)

    def start(self) -> None:
        from signal_lab.operations.scheduler import LIQUIDITY_REFRESH_JOB, JobScheduler, JobWatcher

        with self.bind():
            scheduler = JobScheduler(self.config, self.config.data_dir)
            scheduler.ensure_preset(LIQUIDITY_REFRESH_JOB)
            self.watcher = JobWatcher(scheduler)
            self.watcher.start()

    def shutdown(self) -> None:
        if self.watcher is not None:
            self.watcher.stop(timeout=None)
            self.watcher = None
