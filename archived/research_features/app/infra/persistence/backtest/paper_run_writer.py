from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.backtest import BacktestEquityPointRecord, BacktestTradeRecord
from app.contracts.backtest_run import StoredBacktestRun
from app.infra.db.schema import BacktestEquityPoint, BacktestRun, BacktestTrade
from app.infra.persistence.backtest.result_store import (
    equity_point_record_from_row,
    replace_run_rows,
    result_signal_counts,
    trade_record_from_row,
)
from app.infra.persistence.backtest.run_record_write_base import RunRecordWriteBase


class PaperRunWriteRepository(RunRecordWriteBase):
    def get_running_paper_run(self, *, run_id: int, engine: str) -> StoredBacktestRun | None:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                return None
            if run.execution_mode != "paper_live" or run.engine != engine or run.status != "running":
                return None
            return self._stored_run(run)

    def store_paper_snapshot(
        self,
        *,
        run_id: int,
        engine: str,
        result,
        default_pair: str,
        metadata: dict[str, Any],
        end_date: datetime,
    ) -> None:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                raise ValueError(f"模拟盘记录不存在: {run_id}")
            if run.execution_mode != "paper_live" or run.engine != engine:
                raise ValueError(f"模拟盘记录类型不匹配: {run_id}")
            replace_run_rows(
                session=session,
                run_id=run.id,
                result=result,
                default_pair=default_pair,
                clear_existing=True,
            )
            buy_count, sell_count, hold_count = result_signal_counts(result)
            run.end_date = end_date
            run.total_candles = int(result.total_candles)
            run.total_signals = len(result.signals)
            run.buy_signals = buy_count
            run.sell_signals = sell_count
            run.hold_signals = hold_count
            run.metadata_info = metadata
            session.flush()

    def list_trade_records(self, run_id: int) -> list[BacktestTradeRecord]:
        with self.database_runtime.session_scope() as session:
            trades = (
                session.query(BacktestTrade)
                .filter(BacktestTrade.backtest_id == run_id)
                .order_by(BacktestTrade.opened_at.asc())
                .all()
            )
            return [trade_record_from_row(item) for item in trades]

    def list_equity_records(self, run_id: int) -> list[BacktestEquityPointRecord]:
        with self.database_runtime.session_scope() as session:
            equity = (
                session.query(BacktestEquityPoint)
                .filter(BacktestEquityPoint.backtest_id == run_id)
                .order_by(BacktestEquityPoint.timestamp.asc())
                .all()
            )
            return [equity_point_record_from_row(item) for item in equity]

    def get_paper_run(self, *, run_id: int, engine: str) -> StoredBacktestRun | None:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                return None
            if run.execution_mode != "paper_live" or run.engine != engine:
                return None
            return self._stored_run(run)

    def set_paper_status(
        self,
        *,
        run_id: int,
        engine: str,
        status: str,
        metadata: dict[str, Any],
    ) -> None:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                return
            if run.execution_mode != "paper_live" or run.engine != engine:
                return
            run.status = status
            run.metadata_info = metadata
            session.flush()
