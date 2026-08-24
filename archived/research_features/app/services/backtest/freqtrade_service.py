from __future__ import annotations

from datetime import datetime

from app.contracts.backtest_result import (
    BacktestReportResponse,
    BacktestPortfolioSummaryResponse,
    BacktestResearchReportResponse,
    BacktestSampleRangesResponse,
    BacktestStrategySummaryResponse,
)
from app.contracts.strategy import StrategyTemplateConfigResponse
from app.services.backtest.freqtrade_execution import FreqtradeExecutionContext, IterationResult
from app.services.backtest.freqtrade_execution import FreqtradeIterationExecutor
from app.services.backtest.freqtrade_research import FreqtradeResearchService
from app.services.backtest.freqtrade_result_builder import FreqtradeResultBuilder
from app.services.backtest.freqtrade_strategy_builder import FreqtradeStrategyBuilder
from app.contracts.backtest import BacktestExecutionResult
from app.contracts.backtest_run import validate_backtest_run_metadata
from app.domain.backtest.backtest_symbols import normalize_backtest_symbols
from app.domain.backtest.scripted_templates import get_template_runtime, template_builder_kind
from app.services.market.market_data_service import MarketDataService
from config import settings
from utils.time_utils import to_utc_naive_datetime


class FreqtradeBacktestService:
    STRATEGY_CLASS_NAME = "HeimdallStrategy"
    SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}

    def __init__(self, market_data_service: MarketDataService) -> None:
        self.market_data_service = market_data_service
        self.strategy_builder = FreqtradeStrategyBuilder(self.STRATEGY_CLASS_NAME)
        self.result_builder = FreqtradeResultBuilder(self.STRATEGY_CLASS_NAME)
        self.iteration_executor = FreqtradeIterationExecutor(
            workspace_root=settings.FREQTRADE_WORKSPACE_DIR,
            strategy_class_name=self.STRATEGY_CLASS_NAME,
            market_data_service=self.market_data_service,
            strategy_builder=self.strategy_builder,
            result_builder=self.result_builder,
        )
        self.research_service = FreqtradeResearchService(
            iteration_executor=self.iteration_executor,
            strategy_builder=self.strategy_builder,
            result_builder=self.result_builder,
        )

    def execute(
        self,
        *,
        strategy,
        portfolio,
        research,
        start_date: datetime,
        end_date: datetime,
        timeframe: str,
        initial_cash: float,
        fee_rate: float,
    ) -> BacktestExecutionResult:
        self._validate_timeframe(timeframe)
        start_date = to_utc_naive_datetime(start_date)
        end_date = to_utc_naive_datetime(end_date)
        data_symbols = self._normalize_symbols(portfolio.symbols)
        fee_ratio = self._fee_ratio(fee_rate)
        selected_config = self.strategy_builder.runtime.validate_timeframe_compatibility(
            strategy.template,
            strategy.config,
            timeframe,
        )
        market_type = selected_config.execution.market_type
        direction = selected_config.execution.direction
        execution_symbols = self._build_execution_symbols(data_symbols, market_type)
        stake_currency = self._validate_stake_currency(execution_symbols)
        context = FreqtradeExecutionContext(
            strategy=strategy,
            portfolio=portfolio,
            research=research,
            timeframe=timeframe,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            fee_ratio=fee_ratio,
            stake_currency=stake_currency,
            data_symbols=data_symbols,
            execution_symbols=execution_symbols,
            market_type=market_type,
            direction=direction,
        )

        train_start, train_end, test_start, test_end = self.research_service.split_sample_range(
            start_date,
            end_date,
            research.in_sample_ratio,
        )

        optimization_summary = None
        optimization_best = None
        if research.optimize_trials > 0 and strategy.parameter_space:
            selected_config, optimization_summary, optimization_best = self.research_service.optimize_strategy(
                context=context,
                optimize_start=train_start or start_date,
                optimize_end=train_end or end_date,
                base_config=selected_config,
            )

        in_sample_result = None
        if train_start and train_end:
            if optimization_best and optimization_best.start_date == train_start and optimization_best.end_date == train_end:
                in_sample_result = IterationResult(
                    label="in_sample",
                    start_date=optimization_best.start_date,
                    end_date=optimization_best.end_date,
                    config=optimization_best.config,
                    execution=optimization_best.execution,
                )
            else:
                in_sample_result = self.iteration_executor.run_iteration(
                    label="in_sample",
                    context=context,
                    strategy_config=selected_config,
                    start_date=train_start,
                    end_date=train_end,
                )

        out_of_sample_result = None
        if test_start and test_end:
            primary_result = self.iteration_executor.run_iteration(
                label="out_of_sample",
                context=context,
                strategy_config=selected_config,
                start_date=test_start,
                end_date=test_end,
            )
            out_of_sample_result = primary_result
        else:
            primary_result = self.iteration_executor.run_iteration(
                label="full_sample",
                context=context,
                strategy_config=selected_config,
                start_date=start_date,
                end_date=end_date,
            )

        research_report = BacktestResearchReportResponse(
            selected_config=selected_config.model_dump(),
            in_sample_ratio=research.in_sample_ratio,
            slippage_bps=research.slippage_bps,
            funding_rate_daily=research.funding_rate_daily,
            optimization=optimization_summary,
            in_sample=self.research_service.serialize_iteration(in_sample_result),
            out_of_sample=self.research_service.serialize_iteration(out_of_sample_result),
            rolling_windows=self.research_service.run_rolling_windows(
                context=context,
                base_config=selected_config,
                start_date=start_date,
                end_date=end_date,
            ),
        )

        if primary_result.execution.report is None:
            raise RuntimeError("回测执行结果缺少报告")
        report = BacktestReportResponse.model_validate(
            primary_result.execution.report
        ).model_copy(
            update={
                "strategy": BacktestStrategySummaryResponse(
                    key=strategy.strategy_key,
                    name=strategy.strategy_name,
                    version=strategy.version,
                    template=strategy.template,
                ),
                "portfolio": BacktestPortfolioSummaryResponse(
                    symbols=data_symbols,
                    max_open_trades=portfolio.max_open_trades,
                    position_size_pct=portfolio.position_size_pct,
                    stake_mode=portfolio.stake_mode,
                    stake_currency=stake_currency,
                ),
                "research": research_report,
            }
        )

        if primary_result.execution.metadata is None:
            raise RuntimeError("回测执行结果缺少元数据")
        execution_model = self._execution_model(strategy.template, selected_config)
        metadata_payload = {
            **dict(primary_result.execution.metadata or {}),
            "engine": "Freqtrade",
            "execution_model": execution_model,
            "strategy_key": strategy.strategy_key,
            "strategy_name": strategy.strategy_name,
            "strategy_version": strategy.version,
            "strategy_template": strategy.template,
            "strategy_notes": strategy.notes,
            "selected_config": selected_config.model_dump(),
            "symbols": data_symbols,
            "execution_symbols": execution_symbols,
            "price_source": "spot_ohlcv",
            "portfolio_label": self._portfolio_label(data_symbols),
            "stake_currency": stake_currency,
            "initial_cash": initial_cash,
            "fee_rate": fee_rate,
            "fee_ratio": fee_ratio,
            "timeframe": timeframe,
            "market_type": market_type,
            "direction": direction,
            "research": research_report,
            "sample_ranges": BacktestSampleRangesResponse(
                requested=self._range_payload(start_date, end_date),
                displayed=self._range_payload(primary_result.start_date, primary_result.end_date),
                in_sample=self._range_payload(train_start, train_end),
                out_of_sample=self._range_payload(test_start, test_end),
            ),
        }
        metadata = validate_backtest_run_metadata(metadata_payload)

        return BacktestExecutionResult(
            total_candles=primary_result.execution.total_candles,
            signals=primary_result.execution.signals,
            trades=primary_result.execution.trades,
            equity_curve=primary_result.execution.equity_curve,
            report=report.model_dump(),
            metadata=metadata.model_dump(),
        )

    def _range_payload(self, start_date: datetime | None, end_date: datetime | None):
        return self.research_service.range_payload(start_date, end_date)

    def _validate_timeframe(self, timeframe: str) -> None:
        if timeframe not in self.SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Freqtrade 回测当前只支持: {', '.join(sorted(self.SUPPORTED_TIMEFRAMES))}")

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        return normalize_backtest_symbols(symbols)

    def _validate_stake_currency(self, symbols: list[str]) -> str:
        quotes = {self._quote_currency(symbol) for symbol in symbols}
        if len(quotes) != 1:
            raise ValueError("组合回测暂时只支持同一计价货币的交易对")
        return next(iter(quotes))

    def _portfolio_label(self, symbols: list[str]) -> str:
        return symbols[0] if len(symbols) == 1 else f"{len(symbols)} symbols"

    def _build_execution_symbols(self, data_symbols: list[str], market_type: str) -> list[str]:
        if market_type != "futures":
            return list(data_symbols)
        execution_symbols: list[str] = []
        for symbol in data_symbols:
            base, quote = self._split_symbol(symbol)
            # Futures backtests reuse spot OHLCV as the pricing source, but Freqtrade still
            # needs a futures-style pair name once trading_mode=futures. We synthesize that
            # execution symbol here so the user can keep working with a single spot dataset.
            # Example:
            # - stored data symbol: BTC/USDT
            # - execution symbol:   BTC/USDT:USDT
            # The execution symbol only exists inside the backtest workspace and result files.
            execution_symbols.append(f"{base}/{quote}:{quote}")
        return execution_symbols

    def _quote_currency(self, symbol: str) -> str:
        _, quote = self._split_symbol(symbol)
        return quote

    def _split_symbol(self, symbol: str) -> tuple[str, str]:
        parts = symbol.split("/")
        if len(parts) != 2:
            raise ValueError(f"无效交易对: {symbol}")
        return parts[0], parts[1].split(":")[0]

    def _fee_ratio(self, fee_rate: float) -> float:
        return fee_rate / 100.0

    def _execution_model(self, template: str, selected_config: StrategyTemplateConfigResponse) -> str:
        if selected_config.risk.trade_plan.enabled:
            return "trade_plan"
        if template_builder_kind(get_template_runtime(template)) == "scripted":
            return "scripted_template"
        return "rules"
