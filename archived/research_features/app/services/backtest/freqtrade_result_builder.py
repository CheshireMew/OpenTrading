from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from freqtrade.data.btanalysis.bt_fileutils import (
    get_latest_backtest_filename,
    load_backtest_data,
    load_backtest_stats,
)

from app.services.backtest.freqtrade_report_builder import FreqtradeReportBuilder
from app.services.backtest.freqtrade_trade_mapper import FreqtradeTradeMapper
from app.contracts.backtest import BacktestExecutionResult, BacktestResearchConfig
from app.contracts.backtest_result import BacktestReportResponse, BacktestReportSnapshotResponse
from app.contracts.backtest_run import BACKTEST_EXECUTION_MODE, validate_backtest_run_metadata
from config import settings


class FreqtradeResultBuilder:
    def __init__(self, strategy_class_name: str) -> None:
        self.strategy_class_name = strategy_class_name
        self.trade_mapper = FreqtradeTradeMapper()
        self.report_builder = FreqtradeReportBuilder()

    def build_execution_result(
        self,
        *,
        results_dir: Path,
        data_symbols: list[str],
        execution_symbols: list[str],
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        total_candles: int,
        initial_cash: float,
        fee_rate: float,
        fee_ratio: float,
        research: BacktestResearchConfig,
    ) -> BacktestExecutionResult:
        result_file = results_dir / get_latest_backtest_filename(results_dir)
        stats = load_backtest_stats(result_file)
        trades_frame = load_backtest_data(result_file, strategy=self.strategy_class_name)
        strategy_stats = stats.get("strategy", {}).get(self.strategy_class_name, {})
        pair_aliases = {
            execution_symbol: data_symbol
            for data_symbol, execution_symbol in zip(data_symbols, execution_symbols, strict=True)
        }

        # Freqtrade writes trades using its execution pair names. When futures mode is backed
        # by spot candles, those names contain the synthetic futures suffix (for example
        # BTC/USDT:USDT). We map them back to the original data symbol here so reports,
        # trade lists and signal records stay aligned with the user's single source dataset.
        raw_trades = self.trade_mapper.build_trade_records(trades_frame, pair_aliases=pair_aliases)
        trades = self.trade_mapper.apply_execution_adjustments(raw_trades, research, end_date)
        signals = self.trade_mapper.build_signal_records(trades)
        equity_curve = self.report_builder.build_equity_curve(
            trades=trades,
            initial_cash=initial_cash,
            start_date=start_date,
            end_date=end_date,
        )
        report = self.report_builder.build_report(
            trades=trades,
            equity_curve=equity_curve,
            initial_cash=initial_cash,
            start_date=start_date,
            end_date=end_date,
        )
        report.symbols = list(data_symbols)
        report.timeframe = timeframe
        metadata = validate_backtest_run_metadata({
            "execution_mode": BACKTEST_EXECUTION_MODE,
            "engine": "Freqtrade",
            "exchange": settings.EXCHANGE_ID,
            "stake_currency": self.report_builder.quote_currency(data_symbols[0]),
            "initial_cash": initial_cash,
            "fee_rate": fee_rate,
            "fee_ratio": fee_ratio,
            "symbols": list(data_symbols),
            "execution_symbols": list(execution_symbols),
            "price_source": "spot_ohlcv",
            "timeframe": timeframe,
            "raw_stats": self.report_snapshot(strategy_stats),
        })
        return BacktestExecutionResult(
            total_candles=total_candles,
            signals=signals,
            trades=trades,
            equity_curve=equity_curve,
            report=report.model_dump(),
            metadata=metadata.model_dump(),
        )

    def extract_metric(self, report: BacktestReportResponse | dict[str, Any], metric: str) -> float | None:
        return self.report_builder.extract_metric(report, metric)

    def report_snapshot(self, report: BacktestReportResponse | dict[str, Any] | None) -> BacktestReportSnapshotResponse | None:
        return self.report_builder.report_snapshot(report)
