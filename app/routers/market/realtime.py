from __future__ import annotations

import asyncio
from fastapi import Depends, Query, WebSocket, WebSocketDisconnect

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_market_query_service, get_market_websocket_service
from app.contracts.dto.market_history import RealtimeResponse
from config import settings
from utils.logger import logger


router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])


@router.get("/realtime", response_model=RealtimeResponse)
async def get_realtime_analysis(
    symbol: str = Query(..., description="交易对，如 BTC/USDT"),
    timeframe: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=settings.API_MAX_LIMIT),
    service = Depends(get_market_query_service),
):
    return await service.get_realtime(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


@router.websocket("/ws/realtime")
async def websocket_realtime(
    websocket: WebSocket,
    service = Depends(get_market_query_service),
    websocket_service = Depends(get_market_websocket_service),
):
    await websocket.accept()
    try:
        params = await websocket_service.parse_params_or_reject(websocket, service.valid_symbols, service.valid_timeframes)
        if params is None:
            return

        while True:
            payload = await service.get_realtime_ws_payload(
                symbol=params["symbol"],
                timeframe=params["timeframe"],
                limit=params["limit"],
                use_ai=params["use_ai"],
            )
            await websocket.send_json(payload.model_dump(mode="json"))
            await asyncio.sleep(settings.WS_UPDATE_INTERVAL)
    except WebSocketDisconnect:
        logger.info("客户端断开实时推送")
    except Exception as exc:
        logger.error(f"WS /ws/realtime 错误: {exc}")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
