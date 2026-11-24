from __future__ import annotations

from fastapi import Depends, Query

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_binance_market_intel_service
from app.contracts.dto.binance.page import BinanceMarketPageResponse
from app.contracts.dto.binance.usdm import BinanceContractResearchDetailResponse
from app.contracts.dto.market_history import MarketHistoryResponse


router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])

BINANCE_CHART_INTERVALS = {"5m", "15m", "1h", "4h", "1d"}


@router.get("/binance/market/observations", response_model=dict[str, dict[str, float | None]])
async def get_market_observations(symbols: str = Query(max_length=4096), extended: bool = False,
        service=Depends(get_binance_market_intel_service)):
    """Shared public observations. Visitors evaluate their own alert rules."""
    requested = set(symbol.upper().replace("/", "") for symbol in symbols.split(",") if symbol)
    if len(requested) > 100:
        from fastapi import HTTPException
        raise HTTPException(422, "At most 100 symbols are allowed")
    snapshot = await service.snapshot_service.get_market_page_snapshot_data()
    groups = {kind: {row["symbol"]: row for row in snapshot.get(kind, {}).get("items", [])}
              for kind in ("spot_ticker", "usdm_ticker", "usdm_mark")}
    page = await service.page.get_page(min_rise_pct=0, limit=100, quote_asset="USDT") if extended else None
    scores = {row.symbol: row for row in page.monitor.items} if page else {}
    oi = {row.symbol: row.oi_change_1h_pct for board in page.contract_boards.values() for row in board.items} if page else {}
    result = {}
    for symbol in requested:
        ticker = groups["spot_ticker"].get(symbol) or groups["usdm_ticker"].get(symbol) or {}
        mark = groups["usdm_mark"].get(symbol) or {}
        score = scores.get(symbol)
        rate = mark.get("funding_rate_pct")
        if rate is None and mark.get("last_funding_rate") is not None:
            rate = mark["last_funding_rate"] * 100
        result[symbol] = {"price": ticker.get("last_price") or mark.get("mark_price"),
            "price_change_24h": ticker.get("price_change_pct"), "funding_rate_pct": rate,
            "breakout_score": max(score.natural_score, score.momentum_score) if score else None,
            "natural": score.natural_score if score else None, "momentum": score.momentum_score if score else None,
            "oi_change_1h_pct": oi.get(symbol)}
    return result


@router.get("/binance/market/page", response_model=BinanceMarketPageResponse)
async def get_binance_market_page(
    min_rise_pct: float = Query(5.0, ge=0.5, le=50.0),
    limit: int = Query(24, ge=1, le=30),
    quote_asset: str = Query("USDT", min_length=2, max_length=10),
    service = Depends(get_binance_market_intel_service),
):
    return await service.page.get_page(
        min_rise_pct=min_rise_pct,
        limit=limit,
        quote_asset=quote_asset,
    )


@router.get("/binance/market/contract_detail", response_model=BinanceContractResearchDetailResponse)
async def get_binance_market_contract_detail(
    symbol: str = Query(..., min_length=3, max_length=32),
    period: str = Query("1h"),
    limit: int = Query(72, ge=1, le=500),
    service = Depends(get_binance_market_intel_service),
):
    return await service.usdm.get_contract_research_detail(symbol=symbol, period=period, limit=limit)


@router.get("/binance/market/klines", response_model=MarketHistoryResponse)
async def get_binance_market_klines(
    symbol: str = Query(..., min_length=3, max_length=32),
    market: str = Query("spot", pattern="^(spot|usdm)$"),
    interval: str = Query("15m"),
    limit: int = Query(1000, ge=1, le=1000),
    start_time: int | None = Query(None, ge=0),
    end_time: int | None = Query(None, ge=0),
    service = Depends(get_binance_market_intel_service),
):
    if interval not in BINANCE_CHART_INTERVALS:
        from app.exceptions import AppError
        raise AppError("Unsupported Binance chart interval", status_code=400)
    return await service.page.get_chart_klines(
        market=market,
        symbol=symbol,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
    )
