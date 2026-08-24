from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, Request

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_index_data_service
from app.rate_limit import limiter
from app.contracts.dto.market_catalog import MarketIndexHistoryResponse, MarketIndexResponse
from app.contracts.market_history import build_ohlcv_points
from app.domain.market.index_catalog import INDEX_CATALOG
from config import settings


router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])


def _index_response(record: Any) -> MarketIndexResponse:
    return MarketIndexResponse(
        symbol=record.symbol,
        name=record.name,
        market=record.market,
        currency=record.currency,
        pricing_symbol=record.pricing_symbol,
        pricing_name=record.pricing_name,
        pricing_currency=record.pricing_currency,
    )


def _index_history_response(record: Any) -> MarketIndexHistoryResponse:
    return MarketIndexHistoryResponse(
        symbol=record.symbol,
        name=record.name,
        market=record.market,
        currency=record.currency,
        native_currency=record.native_currency,
        timeframe=record.timeframe,
        source=record.source,
        price_basis=record.price_basis,
        pricing_symbol=record.pricing_symbol,
        pricing_name=record.pricing_name,
        pricing_currency=record.pricing_currency,
        is_close_only=record.is_close_only,
        count=record.count,
        data=build_ohlcv_points([item.as_row() for item in record.data]),
    )


@router.get("/indexes", response_model=list[MarketIndexResponse])
async def list_market_indexes(
):
    return [_index_response(record) for record in INDEX_CATALOG.values()]


@router.get("/indexes/history", response_model=MarketIndexHistoryResponse)
@limiter.limit(settings.RATE_LIMIT_HISTORY)
async def get_index_history(
    request: Request,
    symbol: str = Query(..., description="指数 symbol, 如 US_SP500 或 CN_CSI300"),
    timeframe: str = Query("1d", description="第一版仅支持 1d"),
    start_date: str = Query("2010-01-01", description="Start Date YYYY-MM-DD"),
    end_date: str | None = Query(None, description="End Date YYYY-MM-DD"),
    service = Depends(get_index_data_service),
):
    return _index_history_response(
        await service.get_history_async(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )
    )


@router.get("/indexes/pricing/history", response_model=MarketIndexHistoryResponse)
@limiter.limit(settings.RATE_LIMIT_HISTORY)
async def get_index_pricing_history(
    request: Request,
    symbol: str = Query(..., description="指数 symbol, 如 US_SP500 或 CN_CSI300"),
    timeframe: str = Query("1d", description="第一版仅支持 1d"),
    start_date: str = Query("2010-01-01", description="Start Date YYYY-MM-DD"),
    end_date: str | None = Query(None, description="End Date YYYY-MM-DD"),
    service = Depends(get_index_data_service),
):
    return _index_history_response(
        await service.get_pricing_history_async(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )
    )


