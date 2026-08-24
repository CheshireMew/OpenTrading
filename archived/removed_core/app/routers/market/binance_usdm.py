from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import runtime_dependency
from app.router_ports.market import BinanceMarketPort
from app.runtime_refs import MARKET_BINANCE_MARKET_INTEL
from app.rate_limit import limiter
from app.contracts.dto.binance.common import BinanceExchangeInfoResponse, BinanceTickerStatsResponse
from app.contracts.dto.binance.usdm import (
    BinanceBasisResponse,
    BinanceFundingHistoryListResponse,
    BinanceFundingInfoResponse,
    BinanceMarkPriceResponse,
    BinanceOpenInterestSnapshotResponse,
    BinanceOpenInterestStatsResponse,
    BinanceRatioSeriesResponse,
    BinanceTakerVolumeResponse,
)
from config import settings


router = APIRouter(tags=["Market Data"])
binance_market_dependency = runtime_dependency(MARKET_BINANCE_MARKET_INTEL)


@router.get("/binance/futures/usdm/exchange_info", response_model=BinanceExchangeInfoResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def get_binance_usdm_exchange_info(
    request: Request,
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_exchange_info()


@router.get("/binance/futures/usdm/ticker_24hr", response_model=BinanceTickerStatsResponse)
async def get_binance_usdm_ticker_24hr(
    symbol: str | None = Query(None),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_ticker_24hr(symbol=symbol)


@router.get("/binance/futures/usdm/mark_price", response_model=BinanceMarkPriceResponse)
async def get_binance_usdm_mark_price(
    symbol: str | None = Query(None),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_mark_price(symbol=symbol)


@router.get("/binance/futures/usdm/funding_info", response_model=BinanceFundingInfoResponse)
async def get_binance_usdm_funding_info(
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_funding_info()


@router.get("/binance/futures/usdm/funding_history", response_model=BinanceFundingHistoryListResponse)
async def get_binance_usdm_funding_history(
    symbol: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    start_time: int | None = Query(None),
    end_time: int | None = Query(None),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_funding_history(
        symbol=symbol,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/binance/futures/usdm/open_interest", response_model=BinanceOpenInterestSnapshotResponse)
async def get_binance_usdm_open_interest(
    symbol: str = Query(...),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_open_interest(symbol=symbol)


@router.get("/binance/futures/usdm/open_interest_stats", response_model=BinanceOpenInterestStatsResponse)
async def get_binance_usdm_open_interest_stats(
    symbol: str = Query(...),
    period: str = Query(...),
    limit: int = Query(30, ge=1, le=500),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_open_interest_stats(symbol=symbol, period=period, limit=limit)


@router.get("/binance/futures/usdm/long_short_ratio", response_model=BinanceRatioSeriesResponse)
async def get_binance_usdm_long_short_ratio(
    symbol: str = Query(...),
    period: str = Query(...),
    limit: int = Query(30, ge=1, le=500),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_long_short_ratio(symbol=symbol, period=period, limit=limit)


@router.get("/binance/futures/usdm/top_trader_accounts", response_model=BinanceRatioSeriesResponse)
async def get_binance_usdm_top_trader_accounts(
    symbol: str = Query(...),
    period: str = Query(...),
    limit: int = Query(30, ge=1, le=500),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_top_trader_accounts(symbol=symbol, period=period, limit=limit)


@router.get("/binance/futures/usdm/top_trader_positions", response_model=BinanceRatioSeriesResponse)
async def get_binance_usdm_top_trader_positions(
    symbol: str = Query(...),
    period: str = Query(...),
    limit: int = Query(30, ge=1, le=500),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_top_trader_positions(symbol=symbol, period=period, limit=limit)


@router.get("/binance/futures/usdm/taker_volume", response_model=BinanceTakerVolumeResponse)
async def get_binance_usdm_taker_volume(
    symbol: str = Query(...),
    period: str = Query(...),
    limit: int = Query(30, ge=1, le=500),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_taker_volume(symbol=symbol, period=period, limit=limit)


@router.get("/binance/futures/usdm/basis", response_model=BinanceBasisResponse)
async def get_binance_usdm_basis(
    pair: str = Query(...),
    contract_type: str = Query(...),
    period: str = Query(...),
    limit: int = Query(30, ge=1, le=500),
    service: BinanceMarketPort = Depends(binance_market_dependency),
):
    return await service.usdm.get_basis(pair=pair, contract_type=contract_type, period=period, limit=limit)
