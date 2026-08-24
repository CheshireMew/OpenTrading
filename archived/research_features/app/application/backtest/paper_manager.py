from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.domain.market.timeframes import timeframe_to_timedelta
from app.exceptions import NotFoundError
from app.contracts.backtest import (
    BacktestPortfolioConfig,
    BacktestResearchConfig,
    BacktestEquityPointRecord,
    BacktestTradeRecord,
    PaperStartCommand,
)
from app.contracts.backtest_result import BacktestPortfolioSummaryResponse, BacktestStrategySummaryResponse
from app.infra.executor import run_compute, run_database
from app.contracts.backtest_run import (
    PAPER_LIVE_ENGINE,
    PAPER_LIVE_EXECUTION_MODE,
    RUN_STATUS_RUNNING,
    RUN_STATUS_STOPPED,
    build_paper_metadata,
    update_paper_metadata,
)
from app.application.backtest.ports import BacktestExecutionEngine, BacktestReportBuilder, BacktestRunReader, PaperRunWriter, StrategyReader
from app.application.paper_run_lifecycle import PaperRunController, PaperRunHost, PaperRunHostedService
from config import settings
from utils.time_utils import to_utc_naive_datetime, utc_now_naive

if TYPE_CHECKING:
    pass


@dataclass(slots=True)
class PaperSyncWindow:
    end_at: datetime | None
    synced_end_ms: int | None
    last_processed: dict[str, int | None]


class PaperRunManager(PaperRunHostedService):
    def __init__(
        self,
        *,
        strategy_query_service: StrategyReader,
        freqtrade_service: BacktestExecutionEngine,
        report_builder: BacktestReportBuilder,
        run_repository: BacktestRunReader,
        paper_runs: PaperRunWriter,
        activate_created_runs: bool,
    ) -> None:
        self.strategy_query_service = strategy_query_service
        self.freqtrade_service = freqtrade_service
        self.report_builder = report_builder
        self.run_repository = run_repository
        self.paper_runs = paper_runs
        self.activate_created_runs = activate_created_runs
        self.paper_host = PaperRunHost(
            PaperRunController(
                engine=PAPER_LIVE_ENGINE,
                run_repository=run_repository,
                paper_runs=paper_runs,
                runtime_state=lambda metadata: metadata.runtime_state.model_dump() if metadata.runtime_state else {},
                tick=self._tick,
                interval_seconds=lambda: float(settings.WS_UPDATE_INTERVAL),
                error_label="模拟盘运行失败",
            )
        )

    async def start_run(self, command: PaperStartCommand) -> dict:
        run_id = await run_compute(lambda: self._create_run(command))
        if self.activate_created_runs:
            self._activate_created_run(run_id)
        return {"success": True, "run_id": run_id, "message": "模拟盘已启动"}

    async def stop_run(self, run_id: int) -> dict:
        await self._stop_and_cancel_run(run_id, status=RUN_STATUS_STOPPED, reason="manual_stop")
        return {"success": True, "run_id": run_id, "message": "模拟盘已停止"}

    async def delete_run(self, run_id: int) -> dict:
        await self._stop_and_cancel_run(run_id, status=RUN_STATUS_STOPPED, reason="manual_delete")

        deleted = await run_database(
            lambda: self.run_repository.delete_run(run_id, PAPER_LIVE_EXECUTION_MODE),
        )
        if not deleted:
            raise NotFoundError(f"模拟盘记录不存在: {run_id}")
        return {"success": True, "run_id": run_id, "message": "模拟盘记录已删除"}

    def _tick(self, run_id: int) -> bool:
        run = self.paper_runs.get_running_paper_run(run_id=run_id, engine=PAPER_LIVE_ENGINE)
        if not run:
            return False
        metadata = run.metadata

        symbols = [str(symbol).strip().upper() for symbol in metadata.symbols if str(symbol).strip()]
        if not symbols:
            raise ValueError("模拟盘缺少 symbols 配置")

        sync_window = self._resolve_sync_window(symbols=symbols, timeframe=run.timeframe, now=utc_now_naive())
        if sync_window.end_at is None or sync_window.synced_end_ms is None:
            return True

        runtime_state = metadata.runtime_state
        last_synced_end_ms = self._optional_int(runtime_state.last_synced_end if runtime_state else None)
        if last_synced_end_ms is not None and sync_window.synced_end_ms <= last_synced_end_ms:
            return True

        if not metadata.strategy_key:
            raise ValueError("模拟盘缺少 strategy_key")
        strategy = self.strategy_query_service.get_strategy_version(metadata.strategy_key, metadata.strategy_version)
        portfolio = self._portfolio_from_metadata(metadata, symbols)
        result = self.freqtrade_service.execute(
            strategy=strategy,
            portfolio=portfolio,
            research=BacktestResearchConfig(),
            start_date=to_utc_naive_datetime(run.start_date or utc_now_naive()),
            end_date=sync_window.end_at,
            timeframe=run.timeframe,
            initial_cash=float(metadata.initial_cash or 0.0),
            fee_rate=float(metadata.fee_rate or 0.0),
        )
        positions = self._build_open_positions(result.trades, timeframe=run.timeframe, end_at=sync_window.end_at)
        runtime_state_payload = {
            "cash_balance": self._cash_balance(
                initial_cash=float(metadata.initial_cash or 0.0),
                trades=result.trades,
            ),
            "last_processed": sync_window.last_processed,
            "last_synced_end": sync_window.synced_end_ms,
            "positions": positions,
        }
        merged_metadata = {
            **metadata.model_dump(),
            **dict(result.metadata or {}),
            "engine": PAPER_LIVE_ENGINE,
            "execution_model": "freqtrade_replay",
            "research": None,
        }
        self.paper_runs.store_paper_snapshot(
            run_id=run.id,
            engine=PAPER_LIVE_ENGINE,
            result=result,
            default_pair=run.symbol,
            metadata=update_paper_metadata(
                merged_metadata,
                runtime_state=runtime_state_payload,
                last_updated=sync_window.end_at.isoformat(),
                report=result.report,
            ),
            end_date=sync_window.end_at,
        )
        return True

    def _create_run(self, command: PaperStartCommand) -> int:
        strategy = self.strategy_query_service.get_strategy_version(command.strategy_key, command.strategy_version)
        now = utc_now_naive()
        symbols = [str(symbol).strip().upper() for symbol in command.portfolio.symbols if str(symbol).strip()]
        sync_window = self._resolve_sync_window(symbols=symbols, timeframe=command.timeframe, now=now)
        initial_report = self.report_builder.build_report(
            trades=[],
            equity_curve=[BacktestEquityPointRecord(timestamp=now, equity=command.initial_cash, pnl_abs=0.0, drawdown_pct=0.0)],
            initial_cash=command.initial_cash,
            start_date=now,
            end_date=now,
        )
        initial_report = initial_report.model_copy(
            update={
                "strategy": BacktestStrategySummaryResponse(
                    key=strategy.strategy_key,
                    name=strategy.strategy_name,
                    version=strategy.version,
                    template=strategy.template,
                ),
                "portfolio": BacktestPortfolioSummaryResponse(
                    symbols=symbols,
                    max_open_trades=command.portfolio.max_open_trades,
                    position_size_pct=command.portfolio.position_size_pct,
                    stake_mode=command.portfolio.stake_mode,
                    stake_currency=self.report_builder.quote_currency(symbols[0]),
                ),
            }
        )
        runtime_state = {
            "cash_balance": command.initial_cash,
            "last_processed": sync_window.last_processed,
            "last_synced_end": sync_window.synced_end_ms,
            "positions": {},
        }
        return self.paper_runs.create_run(
            symbol=symbols[0] if len(symbols) == 1 else "PORTFOLIO",
            timeframe=command.timeframe,
            start_date=now,
            end_date=now,
            status=RUN_STATUS_RUNNING,
            execution_mode=PAPER_LIVE_EXECUTION_MODE,
            engine=PAPER_LIVE_ENGINE,
            metadata=build_paper_metadata(
                strategy=strategy,
                symbols=symbols,
                initial_cash=command.initial_cash,
                fee_rate=command.fee_rate,
                portfolio=command.portfolio,
                runtime_state=runtime_state,
                paper_live={
                    "cash_balance": command.initial_cash,
                    "open_positions": 0,
                    "positions": [],
                    "last_updated": now.isoformat(),
                },
                report=initial_report,
            ),
            initial_equity=BacktestEquityPointRecord(
                timestamp=now,
                equity=command.initial_cash,
                pnl_abs=0.0,
                drawdown_pct=0.0,
            ),
        )

    def _resolve_sync_window(self, *, symbols: list[str], timeframe: str, now: datetime) -> PaperSyncWindow:
        timeframe_delta = timeframe_to_timedelta(timeframe)
        timeframe_ms = int(timeframe_delta.total_seconds() * 1000)
        scan_start = now - (timeframe_delta * 3)
        cutoff_ms = int(now.timestamp() * 1000)
        last_processed: dict[str, int | None] = {}
        closed_values: list[int] = []
        for symbol in symbols:
            candles = self.freqtrade_service.market_data_service.load_live_ohlcv_range(
                symbol,
                timeframe,
                scan_start,
                now,
            ).rows
            closed = [row for row in candles if row[0] + timeframe_ms <= cutoff_ms]
            latest_closed = int(closed[-1][0]) if closed else None
            last_processed[symbol] = latest_closed
            if latest_closed is not None:
                closed_values.append(latest_closed)
        if len(closed_values) != len(symbols):
            return PaperSyncWindow(end_at=None, synced_end_ms=None, last_processed=last_processed)
        synced_end_ms = min(closed_values)
        end_at = datetime.utcfromtimestamp(synced_end_ms / 1000.0)
        return PaperSyncWindow(end_at=end_at, synced_end_ms=synced_end_ms, last_processed=last_processed)

    def _build_open_positions(
        self,
        trades: list[BacktestTradeRecord],
        *,
        timeframe: str,
        end_at: datetime | None,
    ) -> dict[str, dict[str, Any]]:
        if end_at is None:
            return {}
        positions: dict[str, dict[str, Any]] = {}
        for trade in trades:
            if trade.closed_at is not None or not trade.pair:
                continue
            candles = self.freqtrade_service.market_data_service.load_ohlcv_range(
                trade.pair,
                timeframe,
                trade.opened_at,
                end_at,
            ).rows
            highs = [float(row[2]) for row in candles] or [trade.entry_price]
            lows = [float(row[3]) for row in candles] or [trade.entry_price]
            last_price = float(candles[-1][4]) if candles else trade.entry_price
            positions[trade.pair] = {
                "symbol": trade.pair,
                "side": trade.side,
                "opened_at": trade.opened_at.isoformat(),
                "entry_price": trade.entry_price,
                "remaining_amount": trade.amount,
                "remaining_cost": trade.stake_amount,
                "highest_price": max(highs),
                "lowest_price": min(lows),
                "last_price": last_price,
                "taken_partial_ids": [],
            }
        return positions

    def _cash_balance(self, *, initial_cash: float, trades: list[BacktestTradeRecord]) -> float:
        realized_profit = sum(item.profit_abs for item in trades if item.closed_at is not None)
        reserved_cost = sum(item.stake_amount for item in trades if item.closed_at is None)
        return initial_cash + realized_profit - reserved_cost

    def _portfolio_from_metadata(self, metadata, symbols: list[str]) -> BacktestPortfolioConfig:
        portfolio = metadata.portfolio
        base = BacktestPortfolioConfig(symbols=symbols)
        return BacktestPortfolioConfig(
            symbols=symbols,
            max_open_trades=int(portfolio.max_open_trades if portfolio and portfolio.max_open_trades is not None else base.max_open_trades),
            position_size_pct=float(portfolio.position_size_pct if portfolio and portfolio.position_size_pct is not None else base.position_size_pct),
            stake_mode=str(portfolio.stake_mode if portfolio and portfolio.stake_mode else base.stake_mode),
        )

    def _optional_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)
