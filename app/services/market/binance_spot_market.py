from __future__ import annotations

from .binance_api_support import BinanceApiSupport, compact_query, encode_symbol_list
from app.application.persistence_ports import BinanceMarketResearchStorePort
from .binance_market_normalizers import normalize_kline_response, normalize_ticker_item
from .binance_research_series import BinanceResearchSeriesLoader


class BinanceSpotMarketService:
    def __init__(self, client: BinanceApiSupport, *, research_store: BinanceMarketResearchStorePort) -> None:
        self.client = client
        self.research_store = research_store
        self.research_series = BinanceResearchSeriesLoader(
            market="spot",
            store=research_store,
            get_json=client.get_json,
        )

    async def get_ticker_24hr(self, *, symbols: list[str] | None = None) -> dict[str, object]:
        payload = await self.client.get_json(
            "/api/v3/ticker/24hr",
            params=compact_query({"symbols": encode_symbol_list(symbols)}),
            ttl=30,
        )
        items = payload if isinstance(payload, list) else [payload]
        return {
            "exchange": "binance",
            "market": "spot",
            "items": [normalize_ticker_item(item) for item in items],
        }

    async def get_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: int | None = None,
        end_time: int | None = None,
        ui_mode: bool = False,
    ) -> dict[str, object]:
        path = "/api/v3/uiKlines" if ui_mode else "/api/v3/klines"
        symbol_key = symbol.upper()
        series = "ui_klines" if ui_mode else "klines"
        params = compact_query(
            {
                "symbol": symbol_key,
                "interval": interval,
                "limit": limit,
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        return await self.research_series.load(
            endpoint=path,
            params=params,
            normalizer=lambda market, payload: normalize_kline_response(market, symbol_key, interval, payload),
            series=series,
            symbol=symbol_key,
            period=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            timestamp_key="open_time",
            response_fields={"symbol": symbol_key, "interval": interval},
        )

