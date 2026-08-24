from __future__ import annotations

from datetime import datetime

from app.contracts.backtest import EvolveStrategyFromBacktestCommand
from app.infra.db.schema import BacktestRun, StrategyVersion
from app.infra.persistence.backtest.run_repository import BacktestRunRepository
from app.application.backtest.strategy_evolution_service import StrategyEvolutionService
from app.application.backtest.strategy_query_service import StrategyQueryService
from app.domain.backtest.strategy_support import normalize_strategy_version_config_model
from app.application.backtest.strategy_write_service import StrategyWriteService
from app.infra.persistence.backtest.strategy_definition_repository import StrategyDefinitionRepository


def _base_config() -> dict:
    return normalize_strategy_version_config_model("ema_rsi_macd", {}).model_dump()


def _evolved_config() -> dict:
    config = _base_config()
    config["risk"]["stoploss"] = -0.06
    return config


def _report_payload() -> dict:
    return {
        "initial_cash": 100000,
        "final_balance": 94000,
        "profit_abs": -6000,
        "profit_pct": -6.0,
        "max_drawdown_pct": 18.0,
        "sharpe": -0.4,
        "calmar": -0.3,
        "profit_factor": 0.72,
        "win_rate": 30.0,
        "total_trades": 10,
        "wins": 3,
        "losses": 7,
        "draws": 0,
        "pair_breakdown": [
            {
                "pair": "BTC/USDT",
                "trades": 10,
                "profit_abs": -6000,
                "profit_pct": -6.0,
                "win_rate": 30.0,
            }
        ],
        "strategy": {
            "key": "ema_rsi_macd",
            "name": "EMA RSI MACD",
            "version": 1,
            "template": "ema_rsi_macd",
        },
        "portfolio": {
            "symbols": ["BTC/USDT"],
            "max_open_trades": 1,
            "position_size_pct": 25,
            "stake_mode": "fixed",
        },
        "research": {
            "selected_config": _base_config(),
            "in_sample_ratio": 70,
            "slippage_bps": 5,
            "funding_rate_daily": 0,
            "optimization": {
                "metric": "profit_pct",
                "trial_count": 2,
                "best_score": 4.2,
                "best_config": _evolved_config(),
                "trials": [],
            },
            "rolling_windows": [],
        },
    }


def test_strategy_evolution_detects_defects_and_persists_new_version(
    db_session,
    installed_database_runtime,
):
    run = BacktestRun(
        symbol="BTC/USDT",
        timeframe="1h",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 6, 1),
        status="completed",
        execution_mode="backtest",
        engine="Freqtrade",
        total_candles=500,
        total_signals=20,
        buy_signals=10,
        sell_signals=10,
        hold_signals=480,
        metadata_info={
            "execution_mode": "backtest",
            "strategy_key": "ema_rsi_macd",
            "strategy_name": "EMA RSI MACD",
            "strategy_version": 1,
            "strategy_template": "ema_rsi_macd",
            "symbols": ["BTC/USDT"],
            "report": _report_payload(),
        },
    )
    db_session.add(run)
    db_session.commit()

    service = StrategyEvolutionService(
        run_repository=BacktestRunRepository(database_runtime=installed_database_runtime),
        strategy_query_service=StrategyQueryService(
            definition_store=StrategyDefinitionRepository(database_runtime=installed_database_runtime)
        ),
        strategy_write_service=StrategyWriteService(
            definition_store=StrategyDefinitionRepository(database_runtime=installed_database_runtime)
        ),
    )
    result = service.evolve_from_backtest(
        EvolveStrategyFromBacktestCommand(
            backtest_id=run.id,
            version_name="EMA RSI MACD evolved",
            make_default=True,
        )
    )

    assert result["created"] is True
    assert result["evolved_version"] is not None
    assert result["evolved_version"]["version"] == 2
    assert "negative_expectancy" in {item["key"] for item in result["defects"]}
    assert any(item["path"] == "risk.stoploss" and item["after"] == -0.06 for item in result["changes"])

    stored = db_session.query(StrategyVersion).filter_by(strategy_key="ema_rsi_macd", version=2).one()
    assert stored.is_default is True
    assert stored.config["risk"]["stoploss"] == -0.06
