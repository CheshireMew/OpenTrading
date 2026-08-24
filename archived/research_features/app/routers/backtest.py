"""
回测相关 API 路由
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import runtime_dependency
from app.exceptions import NotFoundError
from app.router_service_ports import BacktestCommandPort, BacktestQueryPort
from app.runtime_refs import BACKTEST_COMMAND_SERVICE, BACKTEST_QUERY_SERVICE
from app.rate_limit import limiter
from app.contracts.dto.backtest import (
    BacktestDetailResponse,
    BacktestDeleteResponse,
    BacktestPreviewResponse,
    BacktestRunResponse,
    BacktestStartResponse,
    StrategyEvolutionResponse,
    StrategyEditorContractResponse,
    StrategyIndicatorEngineResponse,
    StrategyIndicatorRegistryResponse,
    StrategyDefinitionResponse,
    StrategyTemplateResponse,
    StrategyVersionResponse,
    PaperStartResponse,
    PaperStopResponse,
)
from app.contracts.backtest import (
    BacktestPreviewCommand,
    BacktestStartCommand,
    CreateIndicatorDefinitionCommand,
    CreateStrategyTemplateCommand,
    CreateStrategyVersionCommand,
    EvolveStrategyFromBacktestCommand,
    PaperStartCommand,
)
from config import settings

router = APIRouter()
backtest_command_dependency = runtime_dependency(BACKTEST_COMMAND_SERVICE)
backtest_query_dependency = runtime_dependency(BACKTEST_QUERY_SERVICE)


@router.post("/backtest/preview", response_model=BacktestPreviewResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def preview_backtest(
    request: Request,
    body: BacktestPreviewCommand,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.preview_backtest(body)


@router.post("/backtest/start", response_model=BacktestStartResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def start_backtest(
    request: Request,
    body: BacktestStartCommand,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.start_backtest(body)


@router.post("/paper/start", response_model=PaperStartResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def start_paper_run(
    request: Request,
    body: PaperStartCommand,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.start_paper_run(body)


@router.post("/paper/{run_id}/stop", response_model=PaperStopResponse)
async def stop_paper_run(
    run_id: int,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.stop_paper_run(run_id)


@router.delete("/backtest/{backtest_id}", response_model=BacktestDeleteResponse)
async def delete_backtest(
    backtest_id: int,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.delete_backtest(backtest_id)


@router.delete("/paper/{run_id}", response_model=BacktestDeleteResponse)
async def delete_paper_run(
    run_id: int,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.delete_paper_run(run_id)


@router.get("/backtest/strategies", response_model=list[StrategyDefinitionResponse])
async def list_strategies(service: BacktestQueryPort = Depends(backtest_query_dependency)):
    return await service.list_strategies()


@router.get("/backtest/templates", response_model=list[StrategyTemplateResponse])
async def list_strategy_templates(service: BacktestQueryPort = Depends(backtest_query_dependency)):
    return await service.list_templates()


@router.get("/backtest/editor-contract", response_model=StrategyEditorContractResponse)
async def get_strategy_editor_contract(service: BacktestQueryPort = Depends(backtest_query_dependency)):
    return await service.get_editor_contract()


@router.post("/backtest/templates", response_model=StrategyTemplateResponse)
async def create_strategy_template(
    body: CreateStrategyTemplateCommand,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.create_template(body)


@router.get("/backtest/indicators", response_model=list[StrategyIndicatorRegistryResponse])
async def list_indicators(service: BacktestQueryPort = Depends(backtest_query_dependency)):
    return await service.list_indicators()


@router.get("/backtest/indicator-engines", response_model=list[StrategyIndicatorEngineResponse])
async def list_indicator_engines(service: BacktestQueryPort = Depends(backtest_query_dependency)):
    return await service.list_indicator_engines()


@router.post("/backtest/indicators", response_model=StrategyIndicatorRegistryResponse)
async def create_indicator(
    body: CreateIndicatorDefinitionCommand,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.create_indicator(body)


@router.post("/backtest/strategies", response_model=StrategyVersionResponse)
async def create_strategy_version(
    body: CreateStrategyVersionCommand,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.create_strategy_version(body)


@router.post("/backtest/{backtest_id}/evolve", response_model=StrategyEvolutionResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def evolve_strategy_from_backtest(
    request: Request,
    backtest_id: int,
    body: EvolveStrategyFromBacktestCommand,
    service: BacktestCommandPort = Depends(backtest_command_dependency),
):
    return await service.evolve_strategy_from_backtest(
        body.model_copy(update={"backtest_id": backtest_id})
    )


@router.get("/backtest/list", response_model=list[BacktestRunResponse])
async def list_backtests(service: BacktestQueryPort = Depends(backtest_query_dependency)):
    return await service.list_runs()


@router.get("/backtest/{backtest_id}", response_model=BacktestDetailResponse)
async def get_backtest(
    backtest_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    service: BacktestQueryPort = Depends(backtest_query_dependency),
):
    result = await service.get_run(backtest_id, page, page_size)
    if result is None:
        raise NotFoundError("回测记录不存在")
    return result


@router.get("/paper/list", response_model=list[BacktestRunResponse])
async def list_paper_runs(service: BacktestQueryPort = Depends(backtest_query_dependency)):
    return await service.list_paper_runs()


@router.get("/paper/{run_id}", response_model=BacktestDetailResponse)
async def get_paper_run(
    run_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    service: BacktestQueryPort = Depends(backtest_query_dependency),
):
    result = await service.get_paper_run(run_id, page, page_size)
    if result is None:
        raise NotFoundError("模拟盘记录不存在")
    return result
