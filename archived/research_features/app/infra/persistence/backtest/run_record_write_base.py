from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.backtest import BacktestEquityPointRecord
from app.contracts.backtest_run import StoredBacktestRun, parse_run_metadata
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import BacktestEquityPoint, BacktestRun


class RunRecordWriteBase:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def create_run(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        status: str,
        execution_mode: str,
        engine: str,
        metadata: dict[str, Any],
        total_candles: int = 0,
        total_signals: int = 0,
        buy_signals: int = 0,
        sell_signals: int = 0,
        hold_signals: int = 0,
        initial_equity: BacktestEquityPointRecord | None = None,
    ) -> int:
        with self.database_runtime.session_scope() as session:
            run = BacktestRun(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                status=status,
                execution_mode=execution_mode,
                engine=engine,
                total_candles=total_candles,
                total_signals=total_signals,
                buy_signals=buy_signals,
                sell_signals=sell_signals,
                hold_signals=hold_signals,
                metadata_info=metadata,
            )
            session.add(run)
            session.flush()
            if initial_equity is not None:
                session.add(
                    BacktestEquityPoint(
                        backtest_id=run.id,
                        timestamp=initial_equity.timestamp,
                        equity=initial_equity.equity,
                        pnl_abs=initial_equity.pnl_abs,
                        drawdown_pct=initial_equity.drawdown_pct,
                    )
                )
                session.flush()
            return int(run.id)

    def get_run(self, run_id: int) -> StoredBacktestRun | None:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                return None
            return self._stored_run(run)

    @staticmethod
    def _stored_run(run: BacktestRun) -> StoredBacktestRun:
        return StoredBacktestRun(
            id=int(run.id),
            symbol=run.symbol,
            timeframe=run.timeframe,
            start_date=run.start_date,
            end_date=run.end_date,
            status=run.status,
            execution_mode=run.execution_mode,
            engine=run.engine,
            metadata=parse_run_metadata(run.metadata_info),
        )
