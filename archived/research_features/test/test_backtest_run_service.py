from __future__ import annotations

from datetime import datetime

from app.infra.db.schema import BacktestRun
from app.contracts.backtest import (
    BacktestExecutionResult,
    BacktestPortfolioConfig,
    BacktestResearchConfig,
    StrategyVersionRecord,
)
from app.contracts.backtest_result import BacktestReportResponse
from app.contracts.backtest_run import validate_backtest_run_metadata
from app.application.backtest.run_service import BacktestRunService
from app.infra.persistence.backtest.backtest_run_writer import BacktestRunWriteRepository
from app.domain.backtest.strategy_support import normalize_strategy_version_config_model


class _FailingExecutionEngine:
    def execute(self, **_kwargs):
        raise ValueError("timeframe incompatible")


class _SuccessfulExecutionEngine:
    def execute(self, **_kwargs):
        return BacktestExecutionResult(
            total_candles=24,
            signals=[],
            trades=[],
            equity_curve=[],
            report=BacktestReportResponse(
                initial_cash=100000,
                final_balance=103500,
                profit_abs=3500,
                profit_pct=3.5,
                max_drawdown_pct=0,
                win_rate=0,
                total_trades=0,
                wins=0,
                losses=0,
                draws=0,
            ).model_dump(),
            metadata=validate_backtest_run_metadata(
                {
                    "sample_ranges": {
                    "requested": {
                        "start": "2024-04-01T00:00:00",
                        "end": "2024-06-01T23:59:59.999999",
                    },
                    "displayed": {
                        "start": "2024-05-14T09:35:59.999999",
                        "end": "2024-06-01T23:59:59.999999",
                    },
                }
                }
            ).model_dump(),
        )


def _strategy() -> StrategyVersionRecord:
    return StrategyVersionRecord(
        strategy_key="demo",
        strategy_name="Demo",
        version=1,
        template="ema_rsi_macd",
        config=normalize_strategy_version_config_model("ema_rsi_macd", {}).model_dump(),
    )


def _portfolio() -> BacktestPortfolioConfig:
    return BacktestPortfolioConfig(
        symbols=["BTC/USDT"],
        max_open_trades=1,
        position_size_pct=5.0,
        stake_mode="fixed",
    )


def _research() -> BacktestResearchConfig:
    return BacktestResearchConfig(
        slippage_bps=5.0,
        funding_rate_daily=0.0,
        in_sample_ratio=70.0,
        optimize_metric="sharpe",
        optimize_trials=0,
        rolling_windows=0,
    )


def test_run_service_persists_failed_run_record(db_session, installed_database_runtime):
    service = BacktestRunService(
        execution_engine=_FailingExecutionEngine(),
        run_writer=BacktestRunWriteRepository(database_runtime=installed_database_runtime),
    )
    result = service.run_backtest(
        strategy=_strategy(),
        portfolio=_portfolio(),
        research=_research(),
        start_date=datetime(2024, 4, 1),
        end_date=datetime(2024, 6, 1),
        timeframe="1h",
        initial_cash=100000.0,
        fee_rate=0.1,
    )

    assert result is None
    run = db_session.query(BacktestRun).order_by(BacktestRun.id.desc()).first()
    assert run is not None
    assert run.status == "failed"
    assert run.metadata_info["error"] == "timeframe incompatible"


def test_run_service_uses_displayed_range_as_canonical_run_range(db_session, installed_database_runtime):
    service = BacktestRunService(
        execution_engine=_SuccessfulExecutionEngine(),
        run_writer=BacktestRunWriteRepository(database_runtime=installed_database_runtime),
    )
    result = service.run_backtest(
        strategy=_strategy(),
        portfolio=_portfolio(),
        research=_research(),
        start_date=datetime(2024, 4, 1),
        end_date=datetime(2024, 6, 1, 23, 59, 59, 999999),
        timeframe="1h",
        initial_cash=100000.0,
        fee_rate=0.1,
        preview_id="preview-1",
        preview_fingerprint="fingerprint-1",
        preview_artifact={
            "strategy_key": "demo",
            "strategy_version": 1,
            "timeframe": "1h",
            "symbols": ["BTC/USDT"],
            "markers": {"BTC/USDT": [{"time": 1710000000000, "kind": "long_entry", "label": "做多入场"}]},
            "diagnostics": [],
        },
    )

    assert result is not None
    run = db_session.get(BacktestRun, result)
    assert run is not None
    assert run.status == "completed"
    assert run.start_date == datetime(2024, 5, 14, 9, 35, 59, 999999)
    assert run.end_date == datetime(2024, 6, 1, 23, 59, 59, 999999)
    assert run.metadata_info["sample_ranges"]["requested"]["start"] == "2024-04-01T00:00:00"
    assert run.metadata_info["preview"]["id"] == "preview-1"
    assert run.metadata_info["preview"]["markers"]["BTC/USDT"][0]["kind"] == "long_entry"
