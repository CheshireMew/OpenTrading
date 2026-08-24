from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import runtime_dependency
from app.router_ports.market import FundingRateAppPort
from app.runtime_refs import MARKET_FUNDING_RATE_APP_SERVICE
from app.rate_limit import limiter
from app.contracts.dto.market import FundingRateHistoryResponse, FundingRateSnapshotResponse, FundingRateSyncResponse
from config import settings


router = APIRouter(tags=["Market Data"])
funding_rate_dependency = runtime_dependency(MARKET_FUNDING_RATE_APP_SERVICE)


@router.get("/funding-rate/current", response_model=FundingRateSnapshotResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def get_current_funding_rate(
    request: Request,
    symbol: str = Query(..., description="合约 symbol，例如 BTCUSDT 或 BTC/USDT:USDT"),
    service: FundingRateAppPort = Depends(funding_rate_dependency),
):
    return await service.get_current_funding_rate(symbol)


@router.post("/funding-rate/sync", response_model=FundingRateSyncResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def sync_funding_rate_history(
    request: Request,
    symbol: str = Query(..., description="合约 symbol，例如 BTCUSDT"),
    start_date: str = Query("2019-09-01", description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，默认当前时间"),
    service: FundingRateAppPort = Depends(funding_rate_dependency),
):
    return await service.sync_funding_rate_history(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/funding-rate/history", response_model=FundingRateHistoryResponse)
async def get_funding_rate_history(
    symbol: str = Query(..., description="合约 symbol，例如 BTCUSDT"),
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int | None = Query(None, ge=1, le=20000),
    service: FundingRateAppPort = Depends(funding_rate_dependency),
):
    return await service.get_funding_rate_history(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
