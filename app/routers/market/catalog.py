from __future__ import annotations

from datetime import datetime

from app.contracts.frontend import FrontendContractRouter
from app.services.market.symbol_catalog import list_market_search_items
from app.contracts.dto.market_catalog import ApiStatusResponse, MarketSymbolSearchResponse
from app.product import APP_VERSION

router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])


@router.get("/symbols", response_model=list[MarketSymbolSearchResponse])
async def list_market_symbols():
    return list_market_search_items()


@router.get("/status", response_model=ApiStatusResponse)
async def get_api_status():
    return ApiStatusResponse(
        status="running",
        version=APP_VERSION,
        framework="FastAPI",
        dependencies="ready",
        timestamp=datetime.now().isoformat(),
    )
