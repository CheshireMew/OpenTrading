from __future__ import annotations

import time
from app.domain.market.quotes import MarketQuote

import pytest

from app.services.market.query_app_service import MarketQueryAppService


class FakeSnapshot:
    def __init__(self, prices: dict[str, float | None]) -> None:
        self.prices = prices

    async def get_current_quote(self, symbol: str):
        now = int(time.time() * 1000)
        return MarketQuote(self.prices.get(symbol), now, now, "websocket_snapshot")


class FakeMarketDataService:
    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.history_calls: list[str] = []
        self.delay_seconds = delay_seconds

    def get_history_data(self, symbol: str, timeframe: str, end_ts: int, limit: int):
        self.history_calls.append(symbol)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return [[(int(time.time() * 1000) // 60000 - 1) * 60000, 1.0, 2.0, 0.5, 456.0, 1000.0]]


class FakeRealtime:
    pass


def make_service(snapshot: FakeSnapshot, market_data_service: FakeMarketDataService) -> MarketQueryAppService:
    service = MarketQueryAppService(
        market_data_service=market_data_service,
        realtime_service=FakeRealtime(),
        binance_snapshot_service=snapshot,
    )
    service.valid_symbols = ["BTC/USDT", "ETH/USDT"]
    service.valid_timeframes = ["1d"]
    return service


@pytest.mark.asyncio
async def test_current_price_prefers_websocket_snapshot():
    market_data_service = FakeMarketDataService()
    service = make_service(FakeSnapshot({"BTC/USDT": 123.0}), market_data_service)

    response = (await service.get_current_price(
        symbol="BTC/USDT",
        timeframe="1d",
    )).model_dump()

    assert response["current_price"] == 123.0
    assert market_data_service.history_calls == []


@pytest.mark.asyncio
async def test_current_price_falls_back_to_cached_history():
    market_data_service = FakeMarketDataService()
    service = make_service(FakeSnapshot({"BTC/USDT": None}), market_data_service)

    response = (await service.get_current_price(
        symbol="BTC/USDT",
        timeframe="1d",
    )).model_dump()

    assert response["current_price"] == 456.0
    assert market_data_service.history_calls == ["BTC/USDT"]


@pytest.mark.asyncio
async def test_current_price_batch_uses_shared_snapshot_first_logic():
    market_data_service = FakeMarketDataService()
    service = make_service(FakeSnapshot({"BTC/USDT": 123.0, "ETH/USDT": None}), market_data_service)

    response = (await service.get_current_price_batch(
        symbols=["BTC/USDT", "ETH/USDT", "BTC/USDT"],
        timeframe="1d",
    )).model_dump()

    assert [item["symbol"] for item in response["items"]] == ["BTC/USDT", "ETH/USDT"]
    assert response["items"][0]["current_price"] == 123.0
    assert response["items"][0]["source"] == "websocket_snapshot"
    assert response["items"][1]["current_price"] == 456.0
    assert response["items"][1]["source"] == "cached_history"
    assert market_data_service.history_calls == ["ETH/USDT"]


@pytest.mark.asyncio
async def test_current_price_batch_runs_fallbacks_concurrently():
    market_data_service = FakeMarketDataService(delay_seconds=0.1)
    service = make_service(FakeSnapshot({"BTC/USDT": None, "ETH/USDT": None}), market_data_service)

    started_at = time.perf_counter()
    response = (await service.get_current_price_batch(
        symbols=["BTC/USDT", "ETH/USDT"],
        timeframe="1d",
    )).model_dump()
    elapsed = time.perf_counter() - started_at

    assert [item["symbol"] for item in response["items"]] == ["BTC/USDT", "ETH/USDT"]
    assert [item["source"] for item in response["items"]] == ["cached_history", "cached_history"]
    assert sorted(market_data_service.history_calls) == ["BTC/USDT", "ETH/USDT"]
    assert elapsed < 0.18
