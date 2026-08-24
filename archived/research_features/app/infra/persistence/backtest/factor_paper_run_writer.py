from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.backtest import BacktestEquityPointRecord, BacktestSignalRecord, BacktestTradeRecord
from app.infra.db.schema import BacktestEquityPoint, BacktestRun
from app.infra.persistence.backtest.result_store import build_signal_rows, build_trade_rows
from app.infra.persistence.backtest.run_record_write_base import RunRecordWriteBase


class FactorPaperRunWriteRepository(RunRecordWriteBase):
    def append_factor_paper_increment(
        self,
        *,
        run_id: int,
        new_signals: list[BacktestSignalRecord],
        new_trades: list[BacktestTradeRecord],
        new_equity_points: list[BacktestEquityPointRecord],
        metadata: dict[str, Any],
        end_date: datetime,
    ) -> None:
        with self.database_runtime.session_scope() as session:
            run = session.query(BacktestRun).filter(BacktestRun.id == run_id).first()
            if not run:
                raise ValueError(f"因子模拟盘记录不存在: {run_id}")
            if new_signals:
                session.bulk_save_objects(build_signal_rows(run_id=run.id, signals=new_signals))
            if new_trades:
                session.bulk_save_objects(build_trade_rows(run_id=run.id, trades=new_trades, default_pair=run.symbol))
            if new_equity_points:
                session.bulk_save_objects([
                    BacktestEquityPoint(
                        backtest_id=run.id,
                        timestamp=item.timestamp,
                        equity=item.equity,
                        pnl_abs=item.pnl_abs,
                        drawdown_pct=item.drawdown_pct,
                    )
                    for item in new_equity_points
                ])
            session.flush()

            run.total_candles += len(new_equity_points)
            run.total_signals += len(new_signals)
            run.buy_signals += sum(1 for item in new_signals if item.signal == "BUY")
            run.sell_signals += sum(1 for item in new_signals if item.signal == "SELL")
            run.hold_signals = max(run.total_candles - run.total_signals, 0)
            run.end_date = end_date
            run.metadata_info = metadata
            session.flush()
