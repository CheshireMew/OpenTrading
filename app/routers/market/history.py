from __future__ import annotations

from typing import Literal

from fastapi import Depends, Query, Request

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_market_query_service
from app.rate_limit import limiter
from app.contracts.dto.market_history import (
    CurrentPriceBatchResponse,
    CurrentPriceResponse,
    KlineTailResponse,
    MarketHistoryBatchResponse,
    MarketHistoryResponse,
)
from config import settings


router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])


@router.get("/history", response_model=MarketHistoryResponse)
async def get_market_history(
    symbol: str = Query(..., description="Symbol eg BTC/USDT"),
    timeframe: str = Query(..., description="Timeframe eg 5m"),
    end_ts: int = Query(..., description="End Timestamp (ms)", gt=0),
    limit: int = Query(settings.HISTORY_DEFAULT_LIMIT, description="Limit", ge=1, le=settings.API_MAX_LIMIT),
    service = Depends(get_market_query_service),
):
    return await service.get_history(
        symbol=symbol,
        timeframe=timeframe,
        end_ts=end_ts,
        limit=limit,
    )


@router.get("/klines/latest", response_model=MarketHistoryResponse)
async def get_latest_klines(
    symbol: str = Query(..., description="Symbol eg BTC/USDT"),
    timeframe: str = Query(..., description="Timeframe eg 5m"),
    limit: int = Query(settings.LIMIT, description="Limit", ge=1, le=settings.API_MAX_LIMIT),
    service = Depends(get_market_query_service),
):
    return await service.get_recent_klines(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


@router.get("/klines/tail", response_model=KlineTailResponse)
async def get_kline_tail(
    symbol: str = Query(..., description="Symbol eg BTC/USDT"),
    timeframe: str = Query(..., description="Timeframe eg 5m"),
    limit: int = Query(2, description="Tail size", ge=1, le=20),
    service = Depends(get_market_query_service),
):
    return await service.get_live_kline_tail(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


@router.get("/price/current", response_model=CurrentPriceResponse)
async def get_current_price(
    symbol: str = Query(..., description="Symbol eg BTC/USDT"),
    timeframe: str = Query("1d", description="Timeframe eg 1d"),
    service = Depends(get_market_query_service),
):
    return await service.get_current_price(
        symbol=symbol,
        timeframe=timeframe,
    )


@router.get("/price/current/batch", response_model=CurrentPriceBatchResponse)
async def get_current_price_batch(
    symbols: list[str] = Query(
        ...,
        description="Symbols eg BTC/USDT",
        min_length=1,
        max_length=settings.PRICE_BATCH_MAX_SYMBOLS,
    ),
    timeframe: str = Query("1d", description="Timeframe eg 1d"),
    service = Depends(get_market_query_service),
):
    return await service.get_current_price_batch(
        symbols=symbols,
        timeframe=timeframe,
    )


@router.get("/full_history", response_model=MarketHistoryResponse)
@limiter.limit(settings.RATE_LIMIT_HISTORY)
async def get_market_full_history(
    request: Request,
    symbol: str = Query(..., description="Symbol eg BTC/USDT"),
    timeframe: str = Query("1d", description="Timeframe eg 1d"),
    start_date: str = Query("2010-01-01", description="Start Date YYYY-MM-DD"),
    fetch_policy: Literal["cache_only", "hydrate"] = Query("hydrate", description="History source policy"),
    service = Depends(get_market_query_service),
):
    return await service.get_full_history(
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date,
        fetch_policy=fetch_policy,
    )


@router.get("/full_history/batch", response_model=MarketHistoryBatchResponse)
@limiter.limit(settings.RATE_LIMIT_HISTORY)
async def get_market_full_history_batch(
    request: Request,
    symbols: list[str] = Query(
        ...,
        description="交易对列表，如 BTC/USDT",
        min_length=1,
        max_length=settings.HISTORY_BATCH_MAX_SYMBOLS,
    ),
    timeframe: str = Query("1d", description="Timeframe eg 1d"),
    start_date: str = Query("2010-01-01", description="Start Date YYYY-MM-DD"),
    fetch_policy: Literal["cache_only", "hydrate"] = Query("hydrate", description="History source policy"),
    service = Depends(get_market_query_service),
):
    return await service.get_full_history_batch(
        symbols=symbols,
        timeframe=timeframe,
        start_date=start_date,
        fetch_policy=fetch_policy,
    )
