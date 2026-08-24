from __future__ import annotations

from datetime import datetime
from typing import Any

from app.application.backtest.ports import BacktestReportBuilder, FactorBacktestRunWriter
from app.application.factors.ports import FactorResearchProvider, FactorSignalCore
from app.contracts.backtest import (
    BacktestPortfolioConfig,
    BacktestResearchConfig,
    BacktestEquityPointRecord,
    BacktestSignalRecord,
    BacktestTradeRecord,
    StrategyVersionRecord,
)
from app.contracts.backtest_run import BACKTEST_EXECUTION_MODE, FACTOR_BLEND_ENGINE, RUN_STATUS_COMPLETED, build_backtest_metadata, parse_run_metadata
from app.domain.backtest.strategy_support import blank_strategy_version_config_model
from app.infra.executor import run_compute
from app.contracts.factor import FactorExecutionConfig
from app.domain.factors.signal_execution_core import FactorSignalContext


class FactorExecutionService:
    def __init__(
        self,
        *,
        factor_service: FactorResearchProvider,
        report_builder: BacktestReportBuilder,
        execution_core: FactorSignalCore,
        factor_backtest_runs: FactorBacktestRunWriter,
    ) -> None:
        self.factor_service = factor_service
        self.report_builder = report_builder
        self.execution_core = execution_core
        self.factor_backtest_runs = factor_backtest_runs

    def run_backtest(self, config: FactorExecutionConfig) -> int:
        research_run_id = config.require_research_run_id()
        research_run, frame = self.factor_service.build_stored_blend_frame(research_run_id)
        if frame.empty:
            raise ValueError("研究结果没有可回测的组合分数。")

        request_payload = research_run.request.model_dump()
        blend = research_run.blend.model_dump()
        symbol = request_payload["symbol"]
        timeframe = request_payload["timeframe"]
        entry_threshold = float(blend.get("entry_threshold", 0.0) if config.entry_threshold is None else config.entry_threshold)
        exit_threshold = float(blend.get("exit_threshold", 0.0) if config.exit_threshold is None else config.exit_threshold)

        label_column = f"label::{request_payload['horizon_bars']}".replace("::", "__")
        rows = [
            {
                "timestamp": row.timestamp,
                "close": float(row.close),
                "composite_score": float(row.composite_score or 0.0),
                "future_return": float(getattr(row, label_column, 0.0) or 0.0),
            }
            for row in frame.itertuples(index=False)
        ]
        context = FactorSignalContext(
            symbol=symbol,
            research_run_id=research_run_id,
            initial_cash=float(config.initial_cash),
            fee_rate=float(config.fee_rate),
            position_size_pct=float(config.position_size_pct),
            stake_mode=config.stake_mode,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            stoploss_pct=config.stoploss_pct,
            takeprofit_pct=config.takeprofit_pct,
            max_hold_bars=config.max_hold_bars,
        )
        batch = self.execution_core.run_batch(
            rows=rows,
            state=self.execution_core.create_state(config.initial_cash),
            context=context,
            force_close=True,
        )
        signals = batch.signals
        trades = batch.trades
        equity_curve = self._decorate_drawdowns(batch.equity_points)
        report = self.report_builder.build_report(
            trades=trades,
            equity_curve=equity_curve,
            initial_cash=config.initial_cash,
            start_date=frame["timestamp"].iloc[0],
            end_date=frame["timestamp"].iloc[-1],
        )

        strategy = StrategyVersionRecord(
            strategy_key="factor_blend",
            strategy_name="Factor Blend",
            version=research_run_id,
            template="factor_blend",
            config=blank_strategy_version_config_model().model_dump(),
            version_name=f"Research {research_run_id}",
        )
        portfolio = BacktestPortfolioConfig(
            symbols=[symbol],
            max_open_trades=1,
            position_size_pct=config.position_size_pct,
            stake_mode=config.stake_mode,
        )
        research = BacktestResearchConfig()
        metadata = parse_run_metadata(
            build_backtest_metadata(
                strategy=strategy,
                symbols=[symbol],
                initial_cash=config.initial_cash,
                fee_rate=config.fee_rate,
                portfolio=portfolio,
                research=research,
            )
        ).model_copy(
            update={
                "factor_research": {
                    "run_id": research_run_id,
                    "dataset_id": research_run.dataset_id,
                    "entry_threshold": entry_threshold,
                    "exit_threshold": exit_threshold,
                    "stoploss_pct": config.stoploss_pct,
                    "takeprofit_pct": config.takeprofit_pct,
                    "max_hold_bars": config.max_hold_bars,
                    "blend": blend,
                },
                "report": report,
            }
        ).model_dump()

        return self._persist_backtest_run(
            symbol=symbol,
            timeframe=timeframe,
            start_date=frame["timestamp"].iloc[0],
            end_date=frame["timestamp"].iloc[-1],
            total_candles=len(frame),
            signals=signals,
            trades=trades,
            equity_curve=equity_curve,
            metadata=metadata,
        )

    async def run_backtest_async(self, config: FactorExecutionConfig) -> int:
        return await run_compute(lambda: self.run_backtest(config))

    def _persist_backtest_run(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        total_candles: int,
        signals: list[BacktestSignalRecord],
        trades: list[BacktestTradeRecord],
        equity_curve: list[BacktestEquityPointRecord],
        metadata: dict[str, Any],
    ) -> int:
        return self.factor_backtest_runs.store_completed_rows(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            status=RUN_STATUS_COMPLETED,
            execution_mode=BACKTEST_EXECUTION_MODE,
            engine=FACTOR_BLEND_ENGINE,
            total_candles=total_candles,
            signals=signals,
            trades=trades,
            equity_curve=equity_curve,
            metadata=metadata,
        )

    def _decorate_drawdowns(self, equity_curve: list[BacktestEquityPointRecord]) -> list[BacktestEquityPointRecord]:
        peak = 0.0
        result = []
        for point in equity_curve:
            peak = max(peak, point.equity)
            drawdown = ((peak - point.equity) / peak * 100.0) if peak else 0.0
            result.append(
                BacktestEquityPointRecord(
                    timestamp=point.timestamp,
                    equity=point.equity,
                    pnl_abs=point.pnl_abs,
                    drawdown_pct=drawdown,
                )
            )
        return result
