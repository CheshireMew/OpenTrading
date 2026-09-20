from typing import Literal
from fastapi import Depends, Query, Request, HTTPException
from app.contracts.frontend import FrontendContractRouter
from app.contracts.local_backtest import (
    LocalBacktestCommand, LocalBacktestCatalog, LocalBacktestRun, LocalBacktestRuns,
    LocalBacktestRecords, LocalBacktestExport, LocalBacktestAction, LocalBacktestPreview,
)
from app.services.local_backtest_service import LocalBacktestService
from app.infra.executor import run_database
from app.contracts.parameter_sweep import (ParameterSweepCommand, ParameterSweepPreview, ParameterSweepView,
    ParameterSweepList, ParameterSweepAction, ParameterSweepEffects)
from app.services.parameter_sweep_service import ParameterSweepService
from app.contracts.research_results import (ResearchResultQuery, ResearchResultPage, ResearchResultEntry,
    ResearchResultImport, ResearchResultRefresh)
from app.services.research_results_catalog import ResearchResultsCatalog
from app.services.backtest_diagnostics_service import BacktestDiagnosticsService
from app.contracts.backtest_diagnostics import BacktestDiagnosticSummary, BacktestTradeChanges, BacktestTradeTimeline

router = FrontendContractRouter(frontend_contract_target="research")


def service(request: Request):
    return LocalBacktestService(request.app.state.runtime_services.infra.database_runtime)


async def invoke(call):
    try:
        return await run_database(call)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/research-results/query', response_model=ResearchResultPage)
async def query_research_results(body: ResearchResultQuery, s=Depends(service)):
    return await invoke(lambda: ResearchResultsCatalog(s).query(**body.model_dump()))


@router.post('/local-backtests/preview', response_model=LocalBacktestPreview)
async def preview_local_backtest(body: LocalBacktestCommand, s=Depends(service)):
    return await invoke(lambda: s.preview(body))


@router.post('/research-results/refresh', response_model=ResearchResultRefresh)
async def refresh_research_results(body: ResearchResultImport, s=Depends(service)):
    from config.settings import BASE_DIR
    return await invoke(lambda: ResearchResultsCatalog(s).refresh(body.roots or [BASE_DIR/'docs/verification']))


@router.get('/research-results/{entry_id}', response_model=ResearchResultEntry)
async def get_research_result(entry_id: str, s=Depends(service)):
    return await invoke(lambda: ResearchResultsCatalog(s).get(entry_id))


@router.get("/local-backtests/strategies", response_model=LocalBacktestCatalog)
async def local_backtest_strategies(s=Depends(service)):
    return await invoke(s.catalog)


@router.post('/parameter-sweeps/preview', response_model=ParameterSweepPreview)
async def preview_parameter_sweep(body: ParameterSweepCommand, s=Depends(service)):
    return await invoke(lambda: ParameterSweepService(s).preview(body))


@router.post('/parameter-sweeps', response_model=ParameterSweepView)
async def create_parameter_sweep(body: ParameterSweepCommand, s=Depends(service)):
    return await invoke(lambda: ParameterSweepService(s).create(body))


@router.get('/parameter-sweeps', response_model=ParameterSweepList)
async def list_parameter_sweeps(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), s=Depends(service)):
    return await invoke(lambda: ParameterSweepService(s).listing(offset, limit))


@router.get('/parameter-sweeps/{sweep_id}', response_model=ParameterSweepView)
async def get_parameter_sweep(sweep_id: str, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=512),
    sort: Literal['return_pct','win_rate','max_drawdown_pct','total_trades'] = 'return_pct', descending: bool = True,
    minimum_trades: int = Query(0, ge=0), s=Depends(service)):
    return await invoke(lambda: ParameterSweepService(s).get(sweep_id, offset, limit, sort, descending, minimum_trades))


@router.post('/parameter-sweeps/{sweep_id}/action', response_model=ParameterSweepView)
async def act_parameter_sweep(sweep_id: str, body: ParameterSweepAction, s=Depends(service)):
    batch=ParameterSweepService(s)
    return await invoke(lambda: batch.resume(sweep_id) if body.action=='resume' else batch.cancel(sweep_id))


@router.get('/parameter-sweeps/{sweep_id}/effects', response_model=ParameterSweepEffects)
async def parameter_sweep_effects(sweep_id: str, s=Depends(service)):
    return await invoke(lambda: ParameterSweepService(s).effects(sweep_id))


@router.get('/parameter-sweeps/{sweep_id}/export', response_model=LocalBacktestExport)
async def export_parameter_sweep(sweep_id: str, s=Depends(service)):
    return await invoke(lambda: ParameterSweepService(s).export(sweep_id))


@router.post("/local-backtests", response_model=LocalBacktestRun)
async def create_local_backtest(body: LocalBacktestCommand, s=Depends(service)):
    return await invoke(lambda: s.create(body))


@router.get("/local-backtests", response_model=LocalBacktestRuns)
async def list_local_backtests(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), archived: bool = False, s=Depends(service)):
    return await invoke(lambda: s.listing(offset, limit, archived))


@router.get("/local-backtests/{run_id}", response_model=LocalBacktestRun)
async def get_local_backtest(run_id: str, s=Depends(service)):
    return await invoke(lambda: s.get(run_id))


@router.get('/local-backtests/{run_id}/diagnostics', response_model=BacktestDiagnosticSummary)
async def local_backtest_diagnostics(run_id: str, equity_kind: Literal['equity', 'execution_equity'] = 'equity', s=Depends(service)):
    return await invoke(lambda: BacktestDiagnosticsService(s).summary(run_id, equity_kind=equity_kind))


@router.get('/local-backtests/{run_id}/trade-changes/{other_id}', response_model=BacktestTradeChanges)
async def local_backtest_trade_changes(run_id: str, other_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), s=Depends(service)):
    return await invoke(lambda: BacktestDiagnosticsService(s).compare(run_id, other_id, offset, limit))


@router.get('/local-backtests/{run_id}/trade-timeline/{trade_id}', response_model=BacktestTradeTimeline)
async def local_backtest_trade_timeline(run_id: str, trade_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), s=Depends(service)):
    return await invoke(lambda: BacktestDiagnosticsService(s).timeline(run_id, trade_id, offset, limit))


@router.get("/local-backtests/{run_id}/records/{kind}", response_model=LocalBacktestRecords)
async def local_backtest_records(run_id: str, kind: Literal["trades", "signals", "fills", "equity", "levels", "candles", "indicators", "events", "execution_equity"],
    offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000), start: int | None = None,
    end: int | None = None, sampled: bool = False, s=Depends(service)):
    return await invoke(lambda: s.sampled_equity(run_id, limit, kind) if kind in {"equity", "execution_equity"} and sampled
                        else s.records(run_id, kind, offset, limit, start, end))


@router.post("/local-backtests/{run_id}/cancel", response_model=LocalBacktestRun)
async def cancel_local_backtest(run_id: str, body: LocalBacktestAction, s=Depends(service)):
    return await invoke(lambda: s.cancel(run_id))


@router.post("/local-backtests/{run_id}/rerun", response_model=LocalBacktestRun)
async def rerun_local_backtest(run_id: str, body: LocalBacktestAction, s=Depends(service)):
    return await invoke(lambda: s.rerun(run_id))


@router.post('/local-backtests/{run_id}/migrate', response_model=LocalBacktestRun)
async def migrate_local_backtest(run_id: str, body: LocalBacktestAction, s=Depends(service)):
    return await invoke(lambda: s.migrate(run_id))


@router.post('/local-backtests/{run_id}/resume', response_model=LocalBacktestRun)
async def resume_local_backtest(run_id: str, body: LocalBacktestAction, s=Depends(service)):
    return await invoke(lambda: s.resume(run_id))


@router.get('/local-backtests/{run_id}/artifacts', response_model=dict)
async def local_backtest_artifacts(run_id: str, s=Depends(service)):
    return await invoke(lambda: s.artifacts(run_id))


@router.post("/local-backtests/{run_id}/archive", response_model=LocalBacktestRun)
async def archive_local_backtest(run_id: str, body: LocalBacktestAction, s=Depends(service)):
    return await invoke(lambda: s.archive(run_id))


@router.get("/local-backtests/{run_id}/export", response_model=LocalBacktestExport)
async def export_local_backtest(run_id: str, format: Literal["json", "trades", "equity"] = "json", s=Depends(service)):
    return await invoke(lambda: s.export(run_id, format))


@router.get("/local-backtests/{run_id}/log", response_model=LocalBacktestExport)
async def log_local_backtest(run_id: str, s=Depends(service)):
    def read():
        path = s.directory(run_id) / "run.log"
        if path.exists():
            with path.open("rb") as f:
                f.seek(max(0, path.stat().st_size - 32000))
                content = f.read().decode("utf-8", errors="replace")
        else:
            content = "尚无运行日志"
        return dict(filename="run.log", content=content, media_type="text/plain")
    return await invoke(read)
