from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domain.market.timeframes import timeframe_to_timedelta
from app.contracts.backtest import BacktestEquityPointRecord, BacktestPortfolioConfig, StrategyVersionRecord
from app.contracts.backtest_run import (
    FACTOR_BLEND_PAPER_ENGINE,
    PAPER_LIVE_EXECUTION_MODE,
    RUN_STATUS_RUNNING,
    build_paper_metadata,
    ensure_paper_runtime_state,
    parse_run_metadata,
)
from app.application.backtest.ports import BacktestReportBuilder, BacktestRunReader, PaperRunWriter
from app.application.factors.ports import FactorPaperPersistence, FactorResearchProvider, FactorSignalCore
from app.domain.backtest.strategy_support import blank_strategy_version_config_model
from app.application.paper_run_lifecycle import PaperRunController, PaperRunHost, PaperRunHostedService
from app.infra.executor import run_compute
from app.contracts.factor import FactorExecutionConfig
from app.domain.factors.signal_execution_core import FactorSignalContext
from config import settings
from utils.time_utils import utc_now_naive

class FactorPaperRunManager(PaperRunHostedService):
    def __init__(
        self,
        *,
        factor_service: FactorResearchProvider,
        run_repository: BacktestRunReader,
        report_builder: BacktestReportBuilder,
        execution_core: FactorSignalCore,
        persistence_service: FactorPaperPersistence,
        paper_runs: PaperRunWriter,
        activate_created_runs: bool,
    ) -> None:
        self.factor_service = factor_service
        self.run_repository = run_repository
        self.report_builder = report_builder
        self.execution_core = execution_core
        self.persistence_service = persistence_service
        self.paper_runs = paper_runs
        self.activate_created_runs = activate_created_runs
        self.paper_host = PaperRunHost(
            PaperRunController(
                engine=FACTOR_BLEND_PAPER_ENGINE,
                run_repository=run_repository,
                paper_runs=paper_runs,
                runtime_state=self._stoppable_runtime_state,
                tick=self._tick,
                interval_seconds=lambda: float(settings.WS_UPDATE_INTERVAL),
                error_label="因子模拟盘运行失败",
            )
        )

    async def start_run(self, config: FactorExecutionConfig) -> dict:
        run_id = await run_compute(lambda: self._create_run(config))
        if self.activate_created_runs:
            self._activate_created_run(run_id)
        return {"success": True, "run_id": run_id, "message": "因子模拟盘已启动"}

    def _tick(self, run_id: int) -> bool:
        run = self.paper_runs.get_running_paper_run(run_id=run_id, engine=FACTOR_BLEND_PAPER_ENGINE)
        if not run:
            return False
        metadata = run.metadata
        research_meta = metadata.factor_research
        research_run, frame = self.factor_service.build_live_blend_frame(research_meta["run_id"])
        if frame.empty:
            return True

        timeframe_delta = timeframe_to_timedelta(run.timeframe)
        now = utc_now_naive()
        symbol = str((metadata.symbols or [run.symbol])[0])
        runtime_state = ensure_paper_runtime_state(metadata.runtime_state.model_dump() if metadata.runtime_state else {}, symbols=[symbol])
        last_processed = int((runtime_state.get("last_processed") or {}).get(symbol, 0) or 0)
        closed = frame.loc[frame["timestamp"].apply(lambda ts: ts + timeframe_delta <= now)].copy()
        if last_processed:
            last_processed_dt = datetime.utcfromtimestamp(last_processed / 1000.0)
            closed = closed.loc[closed["timestamp"] > last_processed_dt]
        if closed.empty:
            return True

        execution_core = self.execution_core
        batch = execution_core.run_batch(
            rows=closed.to_dict("records"),
            state=execution_core.create_state(
                float(runtime_state.get("cash_balance", metadata.initial_cash or 0.0)),
                position=execution_core.deserialize_position((runtime_state.get("positions") or {}).get(symbol)),
                held_bars=int(runtime_state.get("held_bars", 0) or 0),
            ),
            context=FactorSignalContext(
                symbol=symbol,
                research_run_id=int(research_meta["run_id"]),
                initial_cash=float(metadata.initial_cash or 0.0),
                fee_rate=float(metadata.fee_rate or 0.0),
                position_size_pct=float(research_meta["position_size_pct"]),
                stake_mode=str(research_meta.get("stake_mode") or "fixed"),
                entry_threshold=float(research_meta["entry_threshold"]),
                exit_threshold=float(research_meta["exit_threshold"]),
                stoploss_pct=float(research_meta["stoploss_pct"]),
                takeprofit_pct=float(research_meta["takeprofit_pct"]),
                max_hold_bars=int(research_meta["max_hold_bars"]),
            ),
        )
        runtime_state["held_bars"] = batch.state.held_bars
        for row in closed.to_dict("records"):
            runtime_state.setdefault("last_processed", {})[symbol] = int(row["timestamp"].timestamp() * 1000)

        self.persistence_service.persist_increment(
            run_id=run.id,
            metadata=metadata,
            runtime_state=runtime_state,
            position=batch.state.position,
            cash_balance=batch.state.cash_balance,
            new_signals=batch.signals,
            new_trades=batch.trades,
            new_equity_points=batch.equity_points,
            now=now,
        )
        return True

    def _create_run(self, config: FactorExecutionConfig) -> int:
        research_run_id = config.require_research_run_id()
        factor_service = self.factor_service
        research_run = factor_service.get_run(research_run_id)
        if not research_run:
            raise ValueError("因子研究记录不存在。")
        request_payload = dict(research_run.get("request") or {})
        blend = dict(research_run.get("blend") or {})
        now = utc_now_naive()
        _, live_frame = factor_service.build_live_blend_frame(research_run_id, end_date=now)
        timeframe_delta = timeframe_to_timedelta(request_payload["timeframe"])
        closed_frame = live_frame.loc[live_frame["timestamp"].apply(lambda ts: ts + timeframe_delta <= now)] if not live_frame.empty else live_frame
        last_processed = None if closed_frame.empty else int(closed_frame["timestamp"].iloc[-1].timestamp() * 1000)
        strategy = StrategyVersionRecord(
            strategy_key="factor_blend",
            strategy_name="Factor Blend",
            version=research_run_id,
            template="factor_blend",
            config=blank_strategy_version_config_model().model_dump(),
        )
        portfolio = BacktestPortfolioConfig(
            symbols=[request_payload["symbol"]],
            max_open_trades=1,
            position_size_pct=config.position_size_pct,
            stake_mode=config.stake_mode,
        )
        report = self.report_builder.build_report(
            trades=[],
            equity_curve=[BacktestEquityPointRecord(timestamp=now, equity=config.initial_cash, pnl_abs=0.0, drawdown_pct=0.0)],
            initial_cash=config.initial_cash,
            start_date=now,
            end_date=now,
        )
        metadata = parse_run_metadata(
            build_paper_metadata(
                strategy=strategy,
                symbols=[request_payload["symbol"]],
                initial_cash=config.initial_cash,
                fee_rate=config.fee_rate,
                portfolio=portfolio,
                runtime_state={
                    "cash_balance": config.initial_cash,
                    "last_processed": {request_payload["symbol"]: last_processed},
                    "positions": {},
                    "held_bars": 0,
                },
                paper_live={"cash_balance": config.initial_cash, "open_positions": 0, "positions": [], "last_updated": now.isoformat()},
                report=report,
            )
        ).model_copy(
            update={
                "factor_research": {
                    "run_id": research_run_id,
                    "dataset_id": research_run["dataset_id"],
                    "entry_threshold": float(blend.get("entry_threshold", 0.0) if config.entry_threshold is None else config.entry_threshold),
                    "exit_threshold": float(blend.get("exit_threshold", 0.0) if config.exit_threshold is None else config.exit_threshold),
                    "stoploss_pct": config.stoploss_pct,
                    "takeprofit_pct": config.takeprofit_pct,
                    "max_hold_bars": config.max_hold_bars,
                    "position_size_pct": config.position_size_pct,
                    "stake_mode": config.stake_mode,
                    "blend": blend,
                },
            }
        ).model_dump()
        return self.paper_runs.create_run(
            symbol=request_payload["symbol"],
            timeframe=request_payload["timeframe"],
            start_date=now,
            end_date=now,
            status=RUN_STATUS_RUNNING,
            execution_mode=PAPER_LIVE_EXECUTION_MODE,
            engine=FACTOR_BLEND_PAPER_ENGINE,
            metadata=metadata,
            initial_equity=BacktestEquityPointRecord(
                timestamp=now,
                equity=config.initial_cash,
                pnl_abs=0.0,
                drawdown_pct=0.0,
            ),
        )

    def _stoppable_runtime_state(self, metadata) -> dict[str, Any]:
        symbol = str((metadata.symbols or [""])[0])
        return ensure_paper_runtime_state(
            metadata.runtime_state.model_dump() if metadata.runtime_state else {},
            symbols=[symbol],
        )
