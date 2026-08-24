from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.infra.executor import run_database
from app.application.persistence_ports import BinanceMarketResearchStorePort

JsonLoader = Callable[..., Awaitable[Any]]
SeriesNormalizer = Callable[[str, Any], dict[str, Any]]


class BinanceResearchSeriesLoader:
    def __init__(
        self,
        *,
        market: str,
        store: BinanceMarketResearchStorePort,
        get_json: JsonLoader,
    ) -> None:
        self.market = market
        self.store = store
        self.get_json = get_json

    async def load(
        self,
        *,
        endpoint: str,
        params: dict[str, Any],
        normalizer: SeriesNormalizer,
        series: str,
        symbol: str,
        period: str = "",
        contract_type: str = "",
        limit: int,
        start_time: int | None = None,
        end_time: int | None = None,
        timestamp_key: str = "timestamp",
        item_key_key: str | None = None,
        response_fields: dict[str, Any] | None = None,
        ttl: int = 30,
    ):
        response_fields = response_fields or {}
        symbol_key = symbol.upper()
        try:
            payload = await self.get_json(endpoint, params=params, ttl=ttl)
        except Exception:
            stored_items = await run_database(
                lambda: self.store.list_items(
                    market=self.market,
                    series=series,
                    symbol=symbol_key,
                    period=period,
                    contract_type=contract_type,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                )
            )
            if stored_items:
                return {
                    "exchange": "binance",
                    "market": self.market,
                    **response_fields,
                    "items": stored_items,
                }
            raise

        response = normalizer(self.market, payload)
        items = response["items"]
        stored_items = await run_database(
            lambda: self.save_and_list(
                series=series,
                symbol=symbol_key,
                items=items,
                period=period,
                contract_type=contract_type,
                timestamp_key=timestamp_key,
                item_key_key=item_key_key,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
        )
        return {
            "exchange": "binance",
            "market": self.market,
            **response_fields,
            "items": stored_items or items,
        }

    def save_and_list(
        self,
        *,
        series: str,
        symbol: str,
        items: list[dict[str, Any]],
        period: str,
        contract_type: str = "",
        timestamp_key: str,
        item_key_key: str | None = None,
        start_time: int | None,
        end_time: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.store.save_items(
            market=self.market,
            series=series,
            symbol=symbol,
            items=items,
            period=period,
            contract_type=contract_type,
            timestamp_key=timestamp_key,
            item_key_key=item_key_key,
        )
        return self.store.list_items(
            market=self.market,
            series=series,
            symbol=symbol,
            period=period,
            contract_type=contract_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
