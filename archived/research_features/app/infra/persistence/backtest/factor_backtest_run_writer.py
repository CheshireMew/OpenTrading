from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.backtest import BacktestEquityPointRecord, BacktestSignalRecord, BacktestTradeRecord
from app.infra.persistence.backtest.result_store import store_run_rows
from app.infra.persistence.backtest.run_record_write_base import RunRecordWriteBase


class FactorBacktestRunWriteRepository(RunRecordWriteBase):
    def store_completed_rows(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        status: str,
        execution_mode: str,
        engine: str,
        total_candles: int,
        signals: list[BacktestSignalRecord],
        trades: list[BacktestTradeRecord],
        equity_curve: list[BacktestEquityPointRecord],
        metadata: dict[str, Any],
    ) -> int:
        run_id = self.create_run(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            status=status,
            execution_mode=execution_mode,
            engine=engine,
            total_candles=total_candles,
            total_signals=len(signals),
            buy_signals=sum(1 for item in signals if item.signal == "BUY"),
            sell_signals=sum(1 for item in signals if item.signal == "SELL"),
            hold_signals=max(total_candles - len(signals), 0),
            metadata=metadata,
        )
        with self.database_runtime.session_scope() as session:
            store_run_rows(
                session=session,
                run_id=run_id,
                signals=signals,
                trades=trades,
                equity_curve=equity_curve,
                default_pair=symbol,
            )
        return run_id
