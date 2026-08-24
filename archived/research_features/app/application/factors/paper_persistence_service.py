from __future__ import annotations

from datetime import datetime
from typing import Any

from app.application.backtest.ports import BacktestReportBuilder, FactorPaperRunWriter, PaperRunWriter
from app.application.factors.ports import FactorSignalCore
from app.contracts.backtest import BacktestEquityPointRecord, BacktestSignalRecord, BacktestTradeRecord
from app.contracts.backtest_metadata import BacktestRunMetadataCommon
from app.contracts.backtest_run import update_paper_metadata
from app.domain.factors.signal_execution_core import FactorSignalPosition


class FactorPaperPersistenceService:
    def __init__(
        self,
        *,
        paper_runs: PaperRunWriter,
        factor_paper_runs: FactorPaperRunWriter,
        report_builder: BacktestReportBuilder,
        execution_core: FactorSignalCore,
    ) -> None:
        self.paper_runs = paper_runs
        self.factor_paper_runs = factor_paper_runs
        self.report_builder = report_builder
        self.execution_core = execution_core

    def persist_increment(
        self,
        *,
        run_id: int,
        metadata: BacktestRunMetadataCommon,
        runtime_state: dict[str, Any],
        position: FactorSignalPosition | None,
        cash_balance: float,
        new_signals: list[BacktestSignalRecord],
        new_trades: list[BacktestTradeRecord],
        new_equity_points: list[BacktestEquityPointRecord],
        now: datetime,
    ) -> None:
        run = self.paper_runs.get_run(run_id)
        if run is None:
            raise ValueError(f"因子模拟盘记录不存在: {run_id}")
        existing_trades = self.paper_runs.list_trade_records(run_id)
        existing_equity = self.paper_runs.list_equity_records(run_id)
        adjusted_equity_points = self._with_running_drawdown(
            existing_equity=existing_equity,
            new_equity_points=new_equity_points,
            initial_cash=float(metadata.initial_cash or 0.0),
        )
        end_date = max((item.timestamp for item in adjusted_equity_points), default=run.end_date or now)
        report = self.report_builder.build_report(
            trades=[*existing_trades, *new_trades],
            equity_curve=[*existing_equity, *adjusted_equity_points],
            initial_cash=float(metadata.initial_cash or 0.0),
            start_date=run.start_date,
            end_date=end_date,
        )
        symbol = str((metadata.symbols or [""])[0])
        serialized_position = self.execution_core.serialize_position(position, symbol=symbol)
        runtime_payload = {
            **{
                key: value
                for key, value in runtime_state.items()
                if key not in {"cash_balance", "positions", "last_processed"}
            },
            "cash_balance": cash_balance,
            "last_processed": dict(runtime_state.get("last_processed") or {}),
            "positions": {symbol: serialized_position} if serialized_position else {},
        }
        self.factor_paper_runs.append_factor_paper_increment(
            run_id=run_id,
            new_signals=new_signals,
            new_trades=new_trades,
            new_equity_points=adjusted_equity_points,
            end_date=end_date,
            metadata=update_paper_metadata(
                metadata,
                runtime_state=runtime_payload,
                last_updated=now.isoformat(),
                report=report,
            ),
        )

    @staticmethod
    def _with_running_drawdown(
        *,
        existing_equity: list[BacktestEquityPointRecord],
        new_equity_points: list[BacktestEquityPointRecord],
        initial_cash: float,
    ) -> list[BacktestEquityPointRecord]:
        peak = max((point.equity for point in existing_equity), default=initial_cash)
        adjusted: list[BacktestEquityPointRecord] = []
        for item in new_equity_points:
            peak = max(peak, item.equity)
            drawdown = ((peak - item.equity) / peak * 100.0) if peak else 0.0
            adjusted.append(
                BacktestEquityPointRecord(
                    timestamp=item.timestamp,
                    equity=item.equity,
                    pnl_abs=item.pnl_abs,
                    drawdown_pct=drawdown,
                )
            )
        return adjusted
