from __future__ import annotations

import asyncio
from datetime import datetime

from app.infra.db.schema import BacktestRun
from app.application.backtest.paper_manager import PaperRunManager
from app.infra.persistence.backtest.run_repository import BacktestRunRepository
from app.infra.persistence.backtest.paper_run_writer import PaperRunWriteRepository


def test_delete_paper_run_updates_stop_state_and_removes_row(installed_database_runtime):
    with installed_database_runtime.session_scope() as session:
        run = BacktestRun(
            symbol="BTC/USDT",
            timeframe="1h",
            start_date=datetime(2026, 3, 28, 10, 0, 0),
            end_date=datetime(2026, 3, 28, 10, 0, 0),
            status="running",
            execution_mode="paper_live",
            engine="FreqtradePaper",
            metadata_info={
                "symbols": ["BTC/USDT"],
                "runtime_state": {
                    "cash_balance": 10000,
                    "last_processed": {"BTC/USDT": None},
                    "last_synced_end": None,
                    "positions": {},
                },
                "paper_live": {
                    "cash_balance": 10000,
                    "open_positions": 0,
                    "positions": [],
                    "last_updated": "2026-03-28T10:00:00",
                },
            },
        )
        session.add(run)
        session.flush()
        run_id = run.id

    manager = PaperRunManager(
        strategy_query_service=object(),
        freqtrade_service=object(),
        report_builder=object(),
        run_repository=BacktestRunRepository(database_runtime=installed_database_runtime),
        paper_runs=PaperRunWriteRepository(database_runtime=installed_database_runtime),
        activate_created_runs=True,
    )

    result = asyncio.run(manager.delete_run(run_id))

    assert result == {"success": True, "run_id": run_id, "message": "模拟盘记录已删除"}
    with installed_database_runtime.session_scope() as session:
        assert session.get(BacktestRun, run_id) is None
