from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.product import api_path
from config.market_data import MarketDataConfig
from app.services.market.liquidity import LiquidityService
from app.services.market.history_jobs import LIQUIDITY_REFRESH_JOB, JobScheduler
from app.infra.persistence.market.history import MarketHistoryDatabase
from app.infra.persistence.market.history.operations import OperationRepository


class LiquidityView:
    """Read liquidity state and execute its explicit refresh command."""

    def __init__(
        self,
        config: MarketDataConfig,
        root: Path,
        database: MarketHistoryDatabase,
    ) -> None:
        self._config = config
        self._root = root.resolve()
        self._operations = OperationRepository(database)

    def liquidity(self, *, days: int = 365, change_days: int = 30) -> dict[str, Any]:
        return LiquidityService(self._root).build(days=days, change_days=change_days)

    def refresh(self, *, request_id: str | None = None) -> dict[str, Any]:
        scheduler = JobScheduler(self._config, self._root)
        job = scheduler.ensure_preset(LIQUIDITY_REFRESH_JOB)
        run = scheduler.run(job.job_id)
        self._operations.append_event(
            level=(
                "error"
                if run.status == "error"
                else "warning"
                if run.status in {"warning", "blocked"}
                else "info"
            ),
            component="web.api",
            event="http_mutation",
            result=run.status,
            correlation_id=request_id or run.run_id,
            parent_correlation_id=run.run_id if request_id else None,
            details={"method": "POST", "path": api_path("/signal-lab/liquidity/refresh")},
        )
        if run.status in {"error", "blocked", "interrupted", "cancelled"}:
            raise RuntimeError(run.summary)
        return {
            "schema_version": "signal-lab.liquidity-refresh.v1",
            "refresh": run.details,
            "run": asdict(run),
            "liquidity": self.liquidity(),
        }
