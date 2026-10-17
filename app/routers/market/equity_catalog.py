from fastapi import Depends, Query

from app.contracts.dto.equity_catalog import EquityCatalogResponse
from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_equity_catalog_service


router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])


@router.get("/equities/catalog", response_model=EquityCatalogResponse)
async def get_equity_catalog(
    refresh: bool = Query(False),
    service=Depends(get_equity_catalog_service),
):
    return await service.get_catalog(refresh=refresh)
