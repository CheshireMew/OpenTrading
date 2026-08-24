from __future__ import annotations

import pytest

from app.contracts.dto.backtest import PaperStartResponse
from app.application.backtest.command_service import BacktestCommandService
from app.contracts.backtest import PaperStartCommand
from app.services.backtest.freqtrade_strategy_builder import FreqtradeStrategyBuilder
from app.services.backtest.strategy_runtime import StrategyRuntime
from app.contracts.backtest import BacktestPortfolioConfig, StrategyVersionRecord
from app.domain.backtest.strategy_support import normalize_strategy_version_config_model


def test_scripted_strategy_builder_emits_freqtrade_code():
    strategy_builder = FreqtradeStrategyBuilder("HeimdallStrategy")

    code = strategy_builder.build_code("btc_regime_pulse_supertrend", "1h", {})
    trade_settings = strategy_builder.trade_settings("btc_regime_pulse_supertrend", {})
    warmup_bars = strategy_builder.warmup_bars("btc_regime_pulse_supertrend", {}, "1h")

    assert "class HeimdallStrategy(IStrategy):" in code
    assert 'timeframe = "1h"' in code
    assert "trend_flip_up" in code
    assert "custom_exit" in code
    assert trade_settings["order_types"]["entry"] == "market"
    assert trade_settings["order_types"]["exit"] == "market"
    assert warmup_bars == 220


def test_scripted_strategy_builds_preview_signal_frame():
    runtime = StrategyRuntime()
    candles: list[list[float]] = []
    base_timestamp = 1_710_000_000_000
    price = 100.0
    for index in range(260):
        drift = 1.2 if index == 120 else (0.25 if index < 180 else -0.35)
        open_price = price
        close_price = price + drift
        high_price = max(open_price, close_price) + 0.8
        low_price = min(open_price, close_price) - 0.8
        volume = 5_000.0 if index in {120, 181} else 1_000.0 + index
        candles.append([base_timestamp + index * 3_600_000, open_price, high_price, low_price, close_price, volume])
        price = close_price

    frame = runtime.build_frame("btc_regime_pulse_supertrend", {}, candles, "1h")

    assert "st_band" in frame.columns
    assert "long_entry_signal" in frame.columns
    assert "short_entry_signal" in frame.columns


class _StrategyQueryServiceStub:
    def get_strategy_version(self, strategy_key: str, version: int | None = None) -> StrategyVersionRecord:
        return StrategyVersionRecord(
            strategy_key=strategy_key,
            strategy_name="BTC Regime Pulse SuperTrend",
            version=version or 1,
            template="btc_regime_pulse_supertrend",
            config=normalize_strategy_version_config_model(
                "btc_regime_pulse_supertrend",
                {},
            ).model_dump(),
        )


class _PaperManagerStub:
    def __init__(self) -> None:
        self.command: PaperStartCommand | None = None

    async def start_run(self, command: PaperStartCommand):  # pragma: no cover
        self.command = command
        return PaperStartResponse(success=True, run_id=88, message="模拟盘已启动")


@pytest.mark.asyncio
async def test_command_service_routes_scripted_strategy_to_paper_manager():
    paper_manager = _PaperManagerStub()
    service = BacktestCommandService(
        run_service=object(),
        preview_service=object(),
        paper_manager=paper_manager,
        run_repository=object(),
        strategy_query_service=_StrategyQueryServiceStub(),
        strategy_write_service=object(),
    )

    command = PaperStartCommand(
        strategy_key="btc_regime_pulse_supertrend",
        strategy_version=1,
        timeframe="1h",
        initial_cash=10_000,
        fee_rate=0.1,
        portfolio=BacktestPortfolioConfig(
            symbols=["BTC/USDT"],
            max_open_trades=1,
            position_size_pct=25,
            stake_mode="fixed",
        ),
    )

    result = await service.start_paper_run(command)

    assert result == PaperStartResponse(success=True, run_id=88, message="模拟盘已启动")
    assert paper_manager.command == command
