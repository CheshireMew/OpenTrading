from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from config import settings


class MarketWebSocketService:
    def parse_params(self, websocket: WebSocket, valid_symbols: list[str], valid_timeframes: list[str]) -> dict[str, Any]:
        symbol = websocket.query_params.get("symbol")
        if not symbol:
            raise ValueError("symbol is required")
        if symbol not in valid_symbols:
            raise ValueError(f"Invalid symbol. Allowed: {valid_symbols}")

        timeframe = websocket.query_params.get("timeframe") or settings.TIMEFRAME
        if timeframe not in valid_timeframes:
            raise ValueError(f"Invalid timeframe. Allowed: {valid_timeframes}")

        try:
            limit = int(websocket.query_params.get("limit") or settings.LIMIT)
            limit = max(1, min(limit, settings.API_MAX_LIMIT))
        except (ValueError, TypeError):
            limit = settings.LIMIT

        use_ai = websocket.query_params.get("ai", "").lower() in ("1", "true", "yes")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "use_ai": use_ai,
        }

    async def parse_params_or_reject(
        self,
        websocket: WebSocket,
        valid_symbols: list[str],
        valid_timeframes: list[str],
    ) -> dict[str, Any] | None:
        try:
            return self.parse_params(websocket, valid_symbols, valid_timeframes)
        except ValueError as exc:
            await self.reject(websocket, str(exc))
            return None

    async def reject(self, websocket: WebSocket, reason: str) -> None:
        await websocket.close(code=1008, reason=reason)
