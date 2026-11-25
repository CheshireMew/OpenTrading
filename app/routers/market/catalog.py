from __future__ import annotations

from datetime import datetime

from app.contracts.frontend import FrontendContractRouter
from app.services.market.symbol_catalog import list_market_search_items
from app.contracts.dto.market_catalog import ApiStatusResponse, MarketSymbolSearchResponse
from app.product import APP_VERSION
from fastapi import Depends
from app.dependencies import get_runtime_services

router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])


@router.get("/symbols", response_model=list[MarketSymbolSearchResponse])
async def list_market_symbols(runtime=Depends(get_runtime_services)):
    items = list_market_search_items()
    workspace = runtime.require_api().chart_workspace
    if workspace is None:
        return items
    from app.services.market.symbol_catalog import get_market_symbol_source
    for instrument in await workspace.market.symbols():
        if instrument.market != "spot":
            continue
        pair = instrument.name
        existing = get_market_symbol_source(pair)
        symbol = pair if existing and existing.exchange_id == instrument.exchange else instrument.id
        if any(item["symbol"] == symbol for item in items):
            continue
        items.append({"symbol": symbol, "name": instrument.name, "asset_class": "crypto", "market": "CRYPTO",
                      "currency": instrument.currency, "exchange": instrument.exchange.upper(),
                      "aliases": [instrument.symbol, instrument.name.split("/")[0]]})
    return items


@router.get("/status", response_model=ApiStatusResponse)
async def get_api_status():
    return ApiStatusResponse(
        status="running",
        version=APP_VERSION,
        framework="FastAPI",
        dependencies="ready",
        timestamp=datetime.now().isoformat(),
    )
