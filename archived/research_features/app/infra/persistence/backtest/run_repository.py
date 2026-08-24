from __future__ import annotations

from typing import Any

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import BacktestEquityPoint, BacktestRun, BacktestSignal, BacktestTrade
from app.infra.persistence.backtest.run_lifecycle import active_run_filters
from app.infra.persistence.backtest.serializers import (
    serialize_backtest_equity_point,
    serialize_backtest_run,
    serialize_backtest_signal,
    serialize_backtest_trade,
)


class BacktestRunRepository:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def list_runs(self, execution_mode: str = "backtest") -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            runs = (
                session.query(BacktestRun)
                .filter(BacktestRun.execution_mode == execution_mode)
                .order_by(BacktestRun.created_at.desc())
                .all()
            )
            return [serialize_backtest_run(run, include_signals=False) for run in runs]

    def get_run(
        self,
        backtest_id: int,
        page: int,
        page_size: int,
        execution_mode: str | None = None,
    ) -> dict[str, Any] | None:
        with self.database_runtime.session_scope() as session:
            query = session.query(BacktestRun).filter(BacktestRun.id == backtest_id)
            if execution_mode:
                query = query.filter(BacktestRun.execution_mode == execution_mode)
            backtest_run = query.first()
            if not backtest_run:
                return None

            total = session.query(BacktestSignal).filter(BacktestSignal.backtest_id == backtest_id).count()
            signals = (
                session.query(BacktestSignal)
                .filter(BacktestSignal.backtest_id == backtest_id)
                .order_by(BacktestSignal.timestamp.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            trades = (
                session.query(BacktestTrade)
                .filter(BacktestTrade.backtest_id == backtest_id)
                .order_by(BacktestTrade.opened_at.asc())
                .all()
            )
            equity_points = (
                session.query(BacktestEquityPoint)
                .filter(BacktestEquityPoint.backtest_id == backtest_id)
                .order_by(BacktestEquityPoint.timestamp.asc())
                .all()
            )

            payload = serialize_backtest_run(backtest_run, include_signals=False)
            payload["signals"] = [serialize_backtest_signal(signal) for signal in signals]
            payload["trades"] = [serialize_backtest_trade(trade) for trade in trades]
            payload["equity_curve"] = [serialize_backtest_equity_point(point) for point in equity_points]
            payload["pagination"] = {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            }
            return payload

    def delete_run(self, backtest_id: int, execution_mode: str | None = None) -> bool:
        with self.database_runtime.session_scope() as session:
            query = session.query(BacktestRun).filter(BacktestRun.id == backtest_id)
            if execution_mode:
                query = query.filter(BacktestRun.execution_mode == execution_mode)
            run = query.first()
            if not run:
                return False

            session.delete(run)
            session.flush()
            return True

    def list_active_run_ids(self, *, execution_mode: str, engine: str) -> list[int]:
        with self.database_runtime.session_scope() as session:
            rows = (
                session.query(BacktestRun.id)
                .filter(*active_run_filters(execution_mode=execution_mode, engine=engine))
                .order_by(BacktestRun.created_at.asc())
                .all()
            )
            return [run_id for (run_id,) in rows]
