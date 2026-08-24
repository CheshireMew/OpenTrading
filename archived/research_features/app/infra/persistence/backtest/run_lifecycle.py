from __future__ import annotations

from datetime import datetime

from sqlalchemy.sql.elements import ColumnElement

from app.contracts.backtest_run import (
    RETENTION_ELIGIBLE_RUN_STATUSES,
    RUN_STATUS_RUNNING,
)
from app.infra.db.schema import BacktestRun


def active_run_filters(*, execution_mode: str, engine: str) -> tuple[ColumnElement[bool], ...]:
    return (
        BacktestRun.status == RUN_STATUS_RUNNING,
        BacktestRun.execution_mode == execution_mode,
        BacktestRun.engine == engine,
    )


def retention_eligible_run_filters(cutoff_dt: datetime) -> tuple[ColumnElement[bool], ...]:
    # Retention is only allowed to remove terminal runs; runtime-restorable rows use the same
    # status/mode/engine boundary as task restoration and must never be selected by age alone.
    return (
        BacktestRun.status.in_(RETENTION_ELIGIBLE_RUN_STATUSES),
        BacktestRun.created_at < cutoff_dt,
    )
