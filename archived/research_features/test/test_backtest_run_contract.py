from __future__ import annotations

from datetime import datetime

import pytest

from app.contracts.backtest import BacktestEquityPointRecord, BacktestPortfolioConfig
from app.domain.backtest.backtest_symbols import normalize_backtest_symbols
from app.infra.db.schema import BacktestRun
from app.contracts.backtest_metadata import BacktestExecutionMetadata
from app.services.backtest.freqtrade_report_builder import FreqtradeReportBuilder
from app.infra.persistence.backtest.run_repository import BacktestRunRepository
from app.contracts.backtest_run import update_paper_metadata
from app.infra.persistence.backtest.serializers import serialize_backtest_run
from app.application.factors.paper_persistence_service import FactorPaperPersistenceService
from app.infra.persistence.backtest.factor_paper_run_writer import FactorPaperRunWriteRepository
from app.infra.persistence.backtest.paper_run_writer import PaperRunWriteRepository


class _NoopFactorExecutionCore:
    def serialize_position(self, position, *, symbol: str):
        return None


def test_repository_filters_by_execution_mode_in_query(db_session, installed_database_runtime):
    db_session.add_all(
        [
            BacktestRun(
                symbol="BTC/USDT",
                timeframe="1h",
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 1, 2),
                status="completed",
                execution_mode="backtest",
                engine="Freqtrade",
                metadata_info={"strategy_key": "alpha"},
            ),
            BacktestRun(
                symbol="ETH/USDT",
                timeframe="1h",
                start_date=datetime(2026, 1, 3),
                end_date=datetime(2026, 1, 4),
                status="running",
                execution_mode="paper_live",
                engine="FreqtradePaper",
                metadata_info={"strategy_key": "beta"},
            ),
        ]
    )
    db_session.flush()
    db_session.commit()

    repository = BacktestRunRepository(database_runtime=installed_database_runtime)
    runs = repository.list_runs("paper_live")

    assert len(runs) == 1
    assert runs[0]["symbol"] == "ETH/USDT"
    assert runs[0]["metadata"]["execution_mode"] == "paper_live"
    assert runs[0]["metadata"]["engine"] == "FreqtradePaper"


def test_serializer_projects_mode_and_engine_from_columns():
    run = BacktestRun(
        id=7,
        symbol="BTC/USDT",
        timeframe="4h",
        start_date=datetime(2026, 2, 1),
        end_date=datetime(2026, 2, 2),
        created_at=datetime(2026, 2, 3),
        status="completed",
        execution_mode="paper_live",
        engine="FactorBlendPaper",
        metadata_info={"strategy_key": "factor_blend", "raw_stats": {"profit_pct": 12.5}},
    )

    payload = serialize_backtest_run(run)

    assert payload["metadata"]["strategy_key"] == "factor_blend"
    assert payload["metadata"]["execution_mode"] == "paper_live"
    assert payload["metadata"]["engine"] == "FactorBlendPaper"
    assert payload["report"] is None
    assert payload["metadata"]["raw_stats"]["profit_pct"] == 12.5


def test_update_paper_metadata_preserves_last_synced_end():
    payload = update_paper_metadata(
        {"symbols": ["BTC/USDT"]},
        runtime_state={
            "cash_balance": 10000,
            "last_processed": {"BTC/USDT": 1710000000000},
            "last_synced_end": 1710000000000,
            "positions": {},
        },
        last_updated="2026-03-28T10:00:00",
    )

    assert payload["runtime_state"]["last_synced_end"] == 1710000000000


def test_update_paper_metadata_preserves_factor_position_entry_score():
    payload = update_paper_metadata(
        {"symbols": ["BTC/USDT"]},
        runtime_state={
            "cash_balance": 10000,
            "last_processed": {"BTC/USDT": 1710000000000},
            "positions": {
                "BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "opened_at": "2026-03-28T10:00:00",
                    "entry_price": 65000,
                    "entry_score": 72.5,
                    "remaining_amount": 0.1,
                    "remaining_cost": 6500,
                    "highest_price": 66000,
                    "lowest_price": 64000,
                    "last_price": 65500,
                }
            },
        },
        last_updated="2026-03-28T10:01:00",
    )

    position = payload["runtime_state"]["positions"]["BTC/USDT"]
    live_position = payload["paper_live"]["positions"][0]
    assert position["entry_score"] == 72.5
    assert live_position["entry_score"] == 72.5


def test_update_paper_metadata_does_not_invent_empty_entry_score():
    payload = update_paper_metadata(
        {"symbols": ["BTC/USDT"]},
        runtime_state={
            "cash_balance": 10000,
            "last_processed": {"BTC/USDT": 1710000000000},
            "positions": {
                "BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "opened_at": "2026-03-28T10:00:00",
                    "entry_price": 65000,
                    "entry_score": None,
                    "remaining_amount": 0.1,
                    "remaining_cost": 6500,
                    "highest_price": 66000,
                    "lowest_price": 64000,
                    "last_price": 65500,
                }
            },
        },
        last_updated="2026-03-28T10:01:00",
    )

    assert payload["runtime_state"]["positions"]["BTC/USDT"]["entry_score"] is None


def test_factor_paper_persistence_increment_uses_backtest_trade_boundary(db_session, installed_database_runtime):
    now = datetime(2026, 3, 28, 10, 0)
    run = BacktestRun(
        symbol="BTC/USDT",
        timeframe="1h",
        start_date=now,
        end_date=now,
        status="running",
        execution_mode="paper_live",
        engine="FactorBlendPaper",
        total_candles=0,
        total_signals=0,
        buy_signals=0,
        sell_signals=0,
        hold_signals=0,
        metadata_info={},
    )
    db_session.add(run)
    db_session.flush()
    db_session.commit()

    service = FactorPaperPersistenceService(
        paper_runs=PaperRunWriteRepository(database_runtime=installed_database_runtime),
        factor_paper_runs=FactorPaperRunWriteRepository(database_runtime=installed_database_runtime),
        report_builder=FreqtradeReportBuilder(),
        execution_core=_NoopFactorExecutionCore(),
    )
    service.persist_increment(
        run_id=run.id,
        metadata=BacktestExecutionMetadata(symbols=["BTC/USDT"], initial_cash=10000),
        runtime_state={"last_processed": {"BTC/USDT": 1710000000000}},
        position=None,
        cash_balance=10000,
        new_signals=[],
        new_trades=[],
        new_equity_points=[
            BacktestEquityPointRecord(timestamp=now, equity=10000, pnl_abs=0, drawdown_pct=0),
        ],
        now=now,
    )

    db_session.refresh(run)
    assert run.metadata_info["runtime_state"]["cash_balance"] == 10000
    assert run.metadata_info["report"]["total_trades"] == 0


def test_backtest_symbol_normalization_uses_market_catalog_boundary():
    symbols = normalize_backtest_symbols(["btc", "ETH/USDT", "btc/usdt"])

    assert symbols == ["BTC/USDT", "ETH/USDT"]


def test_backtest_symbol_normalization_rejects_unknown_symbol():
    with pytest.raises(ValueError, match="回测不支持的交易对"):
        normalize_backtest_symbols(["BAD\\USDT"])
