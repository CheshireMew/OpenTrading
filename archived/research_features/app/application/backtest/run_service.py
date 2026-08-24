from __future__ import annotations

from datetime import datetime

from app.contracts.backtest import BacktestPortfolioConfig, BacktestResearchConfig, StrategyVersionRecord
from app.contracts.backtest_metadata import BacktestRunMetadata
from app.contracts.backtest_run import (
    BACKTEST_EXECUTION_MODE,
    FREQTRADE_ENGINE,
    RUN_STATUS_RUNNING,
    build_completed_run_metadata,
    build_backtest_metadata,
    build_failed_run_metadata,
    parse_run_metadata,
)
from app.application.backtest.ports import BacktestExecutionEngine, BacktestRunWriter
from config import settings
from utils.logger import logger


class BacktestRunService:
    def __init__(self, *, execution_engine: BacktestExecutionEngine, run_writer: BacktestRunWriter) -> None:
        self.execution_engine = execution_engine
        self.run_writer = run_writer

    def run_backtest(
        self,
        *,
        strategy: StrategyVersionRecord,
        portfolio: BacktestPortfolioConfig,
        research: BacktestResearchConfig,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = settings.TIMEFRAME,
        initial_cash: float = settings.BACKTEST_INITIAL_CASH,
        fee_rate: float = settings.BACKTEST_DEFAULT_FEE_RATE,
        preview_id: str | None = None,
        preview_fingerprint: str | None = None,
        preview_artifact: dict | None = None,
    ) -> int | None:
        symbols = list(portfolio.symbols)
        display_symbol = symbols[0] if len(symbols) == 1 else "PORTFOLIO"
        logger.info(
            f"开始回测: engine={FREQTRADE_ENGINE}, strategy={strategy.strategy_key} v{strategy.version}, "
            f"symbols={','.join(symbols)}, range=({start_date} - {end_date})"
        )
        backtest_id = self._create_run_record(
            strategy=strategy,
            portfolio=portfolio,
            research=research,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            display_symbol=display_symbol,
            symbols=symbols,
            preview_id=preview_id,
            preview_fingerprint=preview_fingerprint,
            preview_artifact=preview_artifact,
        )
        try:
            result = self.execution_engine.execute(
                strategy=strategy,
                portfolio=portfolio,
                research=research,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                initial_cash=initial_cash,
                fee_rate=fee_rate,
            )
        except Exception as exc:
            logger.error(f"{FREQTRADE_ENGINE} 回测执行失败: {exc}", exc_info=True)
            self._mark_run_failed(backtest_id=backtest_id, error=str(exc))
            return None
        self._store_completed_run(
            backtest_id=backtest_id,
            result=result,
            default_pair=display_symbol,
        )
        return backtest_id

    def _create_run_record(
        self,
        *,
        strategy: StrategyVersionRecord,
        portfolio: BacktestPortfolioConfig,
        research: BacktestResearchConfig,
        start_date: datetime,
        end_date: datetime,
        timeframe: str,
        initial_cash: float,
        fee_rate: float,
        display_symbol: str,
        symbols: list[str],
        preview_id: str | None,
        preview_fingerprint: str | None,
        preview_artifact: dict | None,
    ) -> int:
        return self.run_writer.create_run(
            symbol=display_symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            status=RUN_STATUS_RUNNING,
            execution_mode=BACKTEST_EXECUTION_MODE,
            engine=FREQTRADE_ENGINE,
            metadata=build_backtest_metadata(
                strategy=strategy,
                symbols=symbols,
                initial_cash=initial_cash,
                fee_rate=fee_rate,
                portfolio=portfolio,
                research=research,
                preview_id=preview_id,
                preview_fingerprint=preview_fingerprint,
                preview_artifact=preview_artifact,
            ),
        )

    def _store_completed_run(self, *, backtest_id: int, result, default_pair: str) -> None:
        stored_run = self.run_writer.get_run(backtest_id)
        if not stored_run:
            raise ValueError(f"回测记录不存在: {backtest_id}")
        merged_metadata = build_completed_run_metadata(
            stored_run.metadata,
            result_metadata=result.metadata,
            report=result.report,
        )
        displayed_start, displayed_end = self._resolve_displayed_range(
            metadata=parse_run_metadata(result.metadata),
            fallback_start=stored_run.start_date,
            fallback_end=stored_run.end_date,
        )
        self.run_writer.store_completed_result(
            run_id=backtest_id,
            result=result,
            default_pair=default_pair,
            metadata=merged_metadata,
            start_date=displayed_start,
            end_date=displayed_end,
            clear_existing=False,
        )
        logger.info(
            f"{FREQTRADE_ENGINE} 回测完成: ID={backtest_id}, candles={result.total_candles}, "
            f"signals={len(result.signals)}"
        )

    def _mark_run_failed(self, *, backtest_id: int, error: str) -> None:
        stored_run = self.run_writer.get_run(backtest_id)
        if not stored_run:
            logger.error(f"无法写入失败状态，回测记录不存在: ID={backtest_id}")
            return
        self.run_writer.mark_run_failed(
            run_id=backtest_id,
            metadata=build_failed_run_metadata(stored_run.metadata, error=error),
        )

    def _resolve_displayed_range(
        self,
        *,
        metadata: BacktestRunMetadata,
        fallback_start: datetime,
        fallback_end: datetime,
    ) -> tuple[datetime, datetime]:
        sample_ranges = getattr(metadata, "sample_ranges", None)
        displayed = sample_ranges.get("displayed") if isinstance(sample_ranges, dict) else None
        if isinstance(displayed, dict):
            start_text = displayed.get("start")
            end_text = displayed.get("end")
        else:
            start_text = displayed.start if displayed else None
            end_text = displayed.end if displayed else None
        if not start_text or not end_text:
            return fallback_start, fallback_end
        return datetime.fromisoformat(start_text), datetime.fromisoformat(end_text)
