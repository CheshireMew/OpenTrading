from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.contracts.backtest import (
    BacktestExecutionResult,
    BacktestPortfolioConfig,
    BacktestResearchConfig,
    StrategyVersionRecord,
)
from app.domain.backtest.backtest_symbols import sanitize_backtest_run_fragment
from app.contracts.strategy import StrategyTemplateConfigResponse
from app.services.backtest.freqtrade_config_builder import FreqtradeConfigBuilder
from app.services.backtest.freqtrade_data_exporter import FreqtradeDataExporter
from app.services.backtest.freqtrade_process_runner import FreqtradeProcessRunner
from app.services.market.market_data_service import MarketDataService


@dataclass(slots=True)
class FreqtradeExecutionContext:
    strategy: StrategyVersionRecord
    portfolio: BacktestPortfolioConfig
    research: BacktestResearchConfig
    timeframe: str
    initial_cash: float
    fee_rate: float
    fee_ratio: float
    stake_currency: str
    data_symbols: list[str]
    execution_symbols: list[str]
    market_type: str
    direction: str


@dataclass(slots=True)
class IterationResult:
    label: str
    start_date: datetime
    end_date: datetime
    config: StrategyTemplateConfigResponse
    execution: BacktestExecutionResult


class FreqtradeIterationExecutor:
    def __init__(
        self,
        *,
        workspace_root: Path,
        strategy_class_name: str,
        market_data_service: MarketDataService,
        strategy_builder: Any,
        result_builder: Any,
        config_builder: FreqtradeConfigBuilder | None = None,
        process_runner: FreqtradeProcessRunner | None = None,
        data_exporter: FreqtradeDataExporter | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.strategy_class_name = strategy_class_name
        self.strategy_file_name = f"{strategy_class_name}.py"
        self.strategy_builder = strategy_builder
        self.result_builder = result_builder
        self.config_builder = config_builder or FreqtradeConfigBuilder()
        self.process_runner = process_runner or FreqtradeProcessRunner(strategy_class_name=strategy_class_name)
        self.data_exporter = data_exporter or FreqtradeDataExporter(
            workspace_root=workspace_root,
            market_data_service=market_data_service,
        )

    def run_iteration(
        self,
        *,
        label: str,
        context: FreqtradeExecutionContext,
        strategy_config: StrategyTemplateConfigResponse,
        start_date: datetime,
        end_date: datetime,
    ) -> IterationResult:
        run_root = self.workspace_root / self._build_run_key(
            context.execution_symbols, context.timeframe, start_date, end_date, label
        )
        user_data_dir = run_root / "user_data"
        strategies_dir = user_data_dir / "strategies"
        results_dir = user_data_dir / "backtest_results"
        config_path = run_root / "config.json"
        strategy_path = strategies_dir / self.strategy_file_name

        if run_root.exists():
            raise RuntimeError(f"Freqtrade 工作目录已存在，拒绝覆盖: {run_root}")
        results_dir.mkdir(parents=True, exist_ok=True)
        strategies_dir.mkdir(parents=True, exist_ok=True)

        total_candles = self.data_exporter.export_history(
            data_symbols=context.data_symbols,
            execution_symbols=context.execution_symbols,
            timeframe=context.timeframe,
            start_date=start_date,
            end_date=end_date,
            warmup_bars=self.strategy_builder.warmup_bars(
                context.strategy.template, strategy_config, context.timeframe
            ),
            market_type=context.market_type,
        )
        strategy_path.write_text(
            self.strategy_builder.build_code(
                context.strategy.template, context.timeframe, strategy_config
            ),
            encoding="utf-8",
        )
        config_path.write_text(
            json.dumps(
                self.config_builder.build(
                    symbols=context.execution_symbols,
                    timeframe=context.timeframe,
                    initial_cash=context.initial_cash,
                    portfolio=context.portfolio,
                    stake_currency=context.stake_currency,
                    market_type=context.market_type,
                    trade_settings=self.strategy_builder.trade_settings(
                        context.strategy.template, strategy_config
                    ),
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.process_runner.run_backtest(
            run_root=run_root,
            config_path=config_path,
            user_data_dir=user_data_dir,
            strategies_dir=strategies_dir,
            data_dir=self.data_exporter.shared_data_dir,
            results_dir=results_dir,
            execution_symbols=context.execution_symbols,
            timeframe=context.timeframe,
            start_date=start_date,
            end_date=end_date,
            fee_ratio=context.fee_ratio,
            label=label,
        )

        execution = self.result_builder.build_execution_result(
            results_dir=results_dir,
            data_symbols=context.data_symbols,
            execution_symbols=context.execution_symbols,
            timeframe=context.timeframe,
            start_date=start_date,
            end_date=end_date,
            total_candles=total_candles,
            initial_cash=context.initial_cash,
            fee_rate=context.fee_rate,
            fee_ratio=context.fee_ratio,
            research=context.research,
        )
        return IterationResult(
            label=label,
            start_date=start_date,
            end_date=end_date,
            config=strategy_config,
            execution=execution,
        )

    def _build_run_key(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        label: str,
    ) -> str:
        unique_suffix = uuid4().hex[:12]
        return (
            f"{self._sanitize_symbol_fragment(symbols)}_{timeframe}_{label}_"
            f"{int(start_date.timestamp())}_{int(end_date.timestamp())}_{unique_suffix}"
        )

    @staticmethod
    def _sanitize_symbol_fragment(symbols: list[str]) -> str:
        base = symbols[0] if len(symbols) == 1 else f"portfolio_{len(symbols)}_{symbols[0]}"
        return sanitize_backtest_run_fragment(base)
