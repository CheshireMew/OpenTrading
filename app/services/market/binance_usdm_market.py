from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.contracts.dto.binance.usdm import BinanceContractResearchDetailResponse
from .binance_api_support import BinanceApiSupport, compact_query
from .binance_market_normalizers import (
    normalize_basis,
    normalize_derivatives_ticker_list,
    normalize_force_orders,
    normalize_kline_response,
    normalize_mark_price_list,
    normalize_open_interest_stats,
    normalize_ratio_series,
    normalize_taker_volume,
)
from .binance_research_series import BinanceResearchSeriesLoader
from app.application.persistence_ports import BinanceMarketResearchStorePort


@dataclass(frozen=True)
class UsdmPeriodSeriesSpec:
    endpoint: str
    series: str
    normalizer: Callable[[str, Any], dict[str, Any]]


PERIOD_SERIES_SPECS = {
    "open_interest": UsdmPeriodSeriesSpec(
        endpoint="/futures/data/openInterestHist",
        series="open_interest_stats",
        normalizer=normalize_open_interest_stats,
    ),
    "global_long_short": UsdmPeriodSeriesSpec(
        endpoint="/futures/data/globalLongShortAccountRatio",
        series="global_long_short_account_ratio",
        normalizer=normalize_ratio_series,
    ),
    "top_trader_accounts": UsdmPeriodSeriesSpec(
        endpoint="/futures/data/topLongShortAccountRatio",
        series="top_trader_account_ratio",
        normalizer=normalize_ratio_series,
    ),
    "top_trader_positions": UsdmPeriodSeriesSpec(
        endpoint="/futures/data/topLongShortPositionRatio",
        series="top_trader_position_ratio",
        normalizer=normalize_ratio_series,
    ),
    "taker_volume": UsdmPeriodSeriesSpec(
        endpoint="/futures/data/takerlongshortRatio",
        series="taker_long_short_ratio",
        normalizer=normalize_taker_volume,
    ),
}


class BinanceUsdmMarketService:
    def __init__(
        self,
        client: BinanceApiSupport,
        *,
        research_store: BinanceMarketResearchStorePort,
    ) -> None:
        self.client = client
        self.research_store = research_store
        self.research_series = BinanceResearchSeriesLoader(
            market="usdm",
            store=research_store,
            get_json=client.get_json,
        )

    async def get_ticker_24hr(self, *, symbol: str | None = None) -> dict[str, object]:
        payload = await self.client.get_json(
            "/fapi/v1/ticker/24hr",
            params=compact_query({"symbol": symbol.upper() if symbol else None}),
            ttl=10,
        )
        return normalize_derivatives_ticker_list("usdm", payload)

    async def get_mark_price(self, *, symbol: str | None = None) -> dict[str, object]:
        payload = await self.client.get_json(
            "/fapi/v1/premiumIndex",
            params=compact_query({"symbol": symbol.upper() if symbol else None}),
            ttl=10,
        )
        return normalize_mark_price_list("usdm", payload)

    async def get_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict[str, object]:
        symbol_key = symbol.upper()
        return await self.research_series.load(
            endpoint="/fapi/v1/klines",
            params=compact_query(
                {
                    "symbol": symbol_key,
                    "interval": interval,
                    "limit": limit,
                    "startTime": start_time,
                    "endTime": end_time,
                }
            ),
            normalizer=lambda market, payload: normalize_kline_response(market, symbol_key, interval, payload),
            series="klines",
            symbol=symbol_key,
            period=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            timestamp_key="open_time",
            response_fields={"symbol": symbol_key, "interval": interval},
        )

    async def get_open_interest_stats(
        self,
        *,
        symbol: str,
        period: str,
        limit: int = 30,
    ) -> dict[str, object]:
        return await self._load_period_series("open_interest", symbol=symbol, period=period, limit=limit)

    def get_cached_open_interest_stats(
        self,
        *,
        symbol: str,
        period: str,
        limit: int = 30,
    ) -> dict[str, object]:
        return {
            "exchange": "binance",
            "market": "usdm",
            "items": self.research_store.list_items(
                market="usdm",
                series="open_interest_stats",
                symbol=symbol,
                period=period,
                limit=limit,
            ),
        }

    async def get_long_short_ratio(self, *, symbol: str, period: str, limit: int = 30) -> dict[str, object]:
        return await self._load_period_series("global_long_short", symbol=symbol, period=period, limit=limit)

    async def get_top_trader_accounts(self, *, symbol: str, period: str, limit: int = 30) -> dict[str, object]:
        return await self._load_period_series("top_trader_accounts", symbol=symbol, period=period, limit=limit)

    async def get_top_trader_positions(self, *, symbol: str, period: str, limit: int = 30) -> dict[str, object]:
        return await self._load_period_series("top_trader_positions", symbol=symbol, period=period, limit=limit)

    async def get_taker_volume(self, *, symbol: str, period: str, limit: int = 30) -> dict[str, object]:
        return await self._load_period_series("taker_volume", symbol=symbol, period=period, limit=limit)

    async def _load_period_series(
        self,
        name: str,
        *,
        symbol: str,
        period: str,
        limit: int,
    ) -> dict[str, object]:
        spec = PERIOD_SERIES_SPECS[name]
        return await self.research_series.load(
            endpoint=spec.endpoint,
            params={"symbol": symbol.upper(), "period": period, "limit": limit},
            normalizer=spec.normalizer,
            series=spec.series,
            symbol=symbol,
            period=period,
            limit=limit,
        )

    async def get_basis(
        self,
        *,
        pair: str,
        contract_type: str,
        period: str,
        limit: int = 30,
    ) -> dict[str, object]:
        return await self.research_series.load(
            endpoint="/futures/data/basis",
            params={"pair": pair.upper(), "contractType": contract_type, "period": period, "limit": limit},
            normalizer=normalize_basis,
            series="basis",
            symbol=pair,
            period=period,
            contract_type=contract_type,
            limit=limit,
        )

    async def get_force_orders(
        self,
        *,
        symbol: str,
        limit: int = 50,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict[str, object]:
        payload = await self.client.get_json(
            "/fapi/v1/allForceOrders",
            params=compact_query(
                {
                    "symbol": symbol.upper(),
                    "limit": limit,
                    "startTime": start_time,
                    "endTime": end_time,
                }
            ),
            ttl=30,
        )
        return normalize_force_orders("usdm", payload)

    async def get_contract_research_detail(
        self,
        *,
        symbol: str,
        period: str = "1h",
        limit: int = 72,
    ) -> BinanceContractResearchDetailResponse:
        symbol_key = symbol.upper()
        return BinanceContractResearchDetailResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "symbol": symbol_key,
            "period": period,
            "open_interest": (await self._safe_series(self.get_open_interest_stats, symbol=symbol_key, period=period, limit=limit)),
            "basis": (await self._safe_series(self.get_basis, pair=symbol_key, contract_type="PERPETUAL", period=period, limit=limit)),
            "taker_volume": (await self._safe_series(self.get_taker_volume, symbol=symbol_key, period=period, limit=limit)),
            "force_orders": (await self._safe_series(self.get_force_orders, symbol=symbol_key, limit=min(limit, 100))),
            "long_short_ratio": (await self._safe_series(self.get_long_short_ratio, symbol=symbol_key, period=period, limit=limit)),
            "top_trader_accounts": (await self._safe_series(self.get_top_trader_accounts, symbol=symbol_key, period=period, limit=limit)),
            "top_trader_positions": (await self._safe_series(self.get_top_trader_positions, symbol=symbol_key, period=period, limit=limit)),
        })

    async def _safe_series(self, loader: Callable[..., Any], **kwargs):
        try:
            return await loader(**kwargs)
        except Exception:
            name = getattr(loader, "__name__", "")
            if name not in {
                "get_open_interest_stats",
                "get_basis",
                "get_taker_volume",
                "get_force_orders",
                "get_long_short_ratio",
                "get_top_trader_accounts",
                "get_top_trader_positions",
            }:
                raise
            return {"exchange": "binance", "market": "usdm", "items": []}

