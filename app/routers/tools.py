"""
工具类 API 路由
"""
from __future__ import annotations

from fastapi import Depends, Query, Request

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_portfolio_analytics_service, get_portfolio_service, get_tools_app_service
from app.infra.executor import run_database
from app.rate_limit import limiter
from app.contracts.dto.tools import (
    DCAResponse,
    PairCompareToolResponse,
    ToolsPageContractResponse,
)
from app.contracts.tools import ComparePairsCommand, DCA_MAX_DAYS, DCA_STRATEGY_KEYS, SimulateDcaCommand
from app.contracts.portfolios import (
    PortfolioCollectionImportCommand,
    PortfolioCollectionChangeCommand,
    PortfolioCollectionResponse,
    PortfolioCollectionSaveCommand,
    PortfolioDeletedPage,
    PortfolioExportDocument,
    PortfolioRestoreCommand,
    PortfolioSimulationResultCommand,
    PortfolioSimulationResultResponse,
    PortfolioLedgerResponse,
    PortfolioTransactionArchiveCommand,
    PortfolioTransactionCreateCommand,
    PortfolioTransactionImportCommand,
    PortfolioTransactionImportResponse,
    PortfolioTransactionResponse,
    PortfolioTransactionUpdateCommand,
    PortfolioAnalyticsCommand,
    PortfolioAnalyticsResponse,
)
from config import settings


router = FrontendContractRouter(frontend_contract_target="tools")


@router.post("/portfolios/{portfolio_id}/analytics", response_model=PortfolioAnalyticsResponse)
async def analyze_portfolio(
    portfolio_id: str,
    body: PortfolioAnalyticsCommand,
    service=Depends(get_portfolio_analytics_service),
):
    return await service.analyze(portfolio_id, body)


@router.get("/contract", response_model=ToolsPageContractResponse)
async def get_tools_contract():
    return ToolsPageContractResponse(
        dca_defaults=SimulateDcaCommand.model_validate({}),
        dca_strategies=list(DCA_STRATEGY_KEYS),
        dca_multiplier_default=settings.DCA_DEFAULT_MULTIPLIER,
        dca_max_days=DCA_MAX_DAYS,
        compare_defaults=ComparePairsCommand.model_validate({}),
    )


@router.post("/dca_simulate", response_model=DCAResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def dca_simulate(
    request: Request,
    body: SimulateDcaCommand,
    service = Depends(get_tools_app_service),
):
    return await service.simulate_dca(body)


@router.post("/compare_pairs", response_model=PairCompareToolResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def compare_pairs(
    request: Request,
    body: ComparePairsCommand,
    service = Depends(get_tools_app_service),
):
    return await service.compare_pairs(body)


@router.get("/portfolios", response_model=PortfolioCollectionResponse)
async def get_portfolio_collection(service=Depends(get_portfolio_service)):
    return await run_database(service.get_collection)


@router.get("/portfolios/{portfolio_id}/ledger", response_model=PortfolioLedgerResponse)
async def get_portfolio_ledger(
    portfolio_id: str,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.get_ledger(portfolio_id))


@router.post("/portfolios/{portfolio_id}/transactions", response_model=PortfolioTransactionResponse)
async def create_portfolio_transaction(
    portfolio_id: str,
    body: PortfolioTransactionCreateCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.create_transaction(portfolio_id, body))


@router.put(
    "/portfolios/{portfolio_id}/transactions/{transaction_id}",
    response_model=PortfolioTransactionResponse,
)
async def update_portfolio_transaction(
    portfolio_id: str,
    transaction_id: str,
    body: PortfolioTransactionUpdateCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(
        lambda: service.update_transaction(portfolio_id, transaction_id, body)
    )


@router.post(
    "/portfolios/{portfolio_id}/transactions/{transaction_id}/archive",
    response_model=PortfolioTransactionResponse,
)
async def archive_portfolio_transaction(
    portfolio_id: str,
    transaction_id: str,
    body: PortfolioTransactionArchiveCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(
        lambda: service.archive_transaction(
            portfolio_id,
            transaction_id,
            body,
            archived=True,
        )
    )


@router.post(
    "/portfolios/{portfolio_id}/transactions/{transaction_id}/restore",
    response_model=PortfolioTransactionResponse,
)
async def restore_portfolio_transaction(
    portfolio_id: str,
    transaction_id: str,
    body: PortfolioTransactionArchiveCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(
        lambda: service.archive_transaction(
            portfolio_id,
            transaction_id,
            body,
            archived=False,
        )
    )


@router.post(
    "/portfolios/{portfolio_id}/transactions/import",
    response_model=PortfolioTransactionImportResponse,
)
async def import_portfolio_transactions(
    portfolio_id: str,
    body: PortfolioTransactionImportCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.import_transactions(portfolio_id, body))


@router.put("/portfolios", response_model=PortfolioCollectionResponse)
async def save_portfolio_collection(
    body: PortfolioCollectionSaveCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.save_collection(body))


@router.patch("/portfolios", response_model=PortfolioCollectionResponse)
async def change_portfolio_collection(
    body: PortfolioCollectionChangeCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.apply_collection_changes(body))


@router.get("/portfolios/deleted", response_model=PortfolioDeletedPage)
async def list_deleted_portfolios(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.list_deleted(offset=offset, limit=limit))


@router.get("/portfolios/export", response_model=PortfolioExportDocument)
async def export_portfolio_collection(service=Depends(get_portfolio_service)):
    return await run_database(service.export_collection)


@router.post("/portfolios/import", response_model=PortfolioCollectionResponse)
async def import_portfolio_collection(
    body: PortfolioCollectionImportCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.import_collection(body))


@router.get(
    "/portfolios/{portfolio_id}/simulation",
    response_model=PortfolioSimulationResultResponse,
)
async def get_portfolio_simulation(
    portfolio_id: str,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.get_simulation(portfolio_id))


@router.put(
    "/portfolios/{portfolio_id}/simulation",
    response_model=PortfolioSimulationResultResponse,
)
async def save_portfolio_simulation(
    portfolio_id: str,
    body: PortfolioSimulationResultCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(lambda: service.save_simulation(portfolio_id, body))


@router.post("/portfolios/{portfolio_id}/restore", response_model=PortfolioCollectionResponse)
async def restore_portfolio(
    portfolio_id: str,
    body: PortfolioRestoreCommand,
    service=Depends(get_portfolio_service),
):
    return await run_database(
        lambda: service.restore_portfolio(portfolio_id, body.expectedRevision)
    )
