from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infra.db.schema import BacktestRun
from app.infra.persistence.backtest.result_store import replace_run_rows, result_signal_counts
from app.infra.persistence.backtest.run_record_write_base import RunRecordWriteBase


class BacktestRunWriteRepository(RunRecordWriteBase):
    def store_completed_result(
        self,
        *,
        run_id: int,
        result,
        default_pair: str,
        metadata: dict[str, Any],
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        clear_existing: bool = False,
    ) -> None:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                raise ValueError(f"回测记录不存在: {run_id}")
            replace_run_rows(
                session=session,
                run_id=run_id,
                result=result,
                default_pair=default_pair,
                clear_existing=clear_existing,
            )
            buy_count, sell_count, hold_count = result_signal_counts(result)
            run.start_date = start_date or run.start_date
            run.end_date = end_date or result.end_date
            run.status = "completed"
            run.total_candles = int(result.total_candles)
            run.total_signals = len(result.signals)
            run.buy_signals = buy_count
            run.sell_signals = sell_count
            run.hold_signals = hold_count
            run.metadata_info = metadata
            session.flush()

    def mark_run_failed(self, *, run_id: int, metadata: dict[str, Any]) -> bool:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                return False
            run.status = "failed"
            run.metadata_info = metadata
            session.flush()
            return True
