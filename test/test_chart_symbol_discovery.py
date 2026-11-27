"""Discover new exchange listings through the same catalog and chart adapters."""
from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.infra.market_data.binance_api import BinanceApiSupport
from app.routers.chart_workspace import router, services
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.services.market.binance_spot_market import BinanceSpotMarketService
from app.services.market.binance_usdm_market import BinanceUsdmMarketService


def listing(base, *, contract="TRADIFI_PERPETUAL", status="TRADING", quote="USDT"):
    return {"symbol": base + quote, "baseAsset": base, "quoteAsset": quote,
            "status": status, "contractType": contract,
            "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {"filterType": "LOT_SIZE", "stepSize": "0.01"}]}


@pytest_asyncio.fixture
async def exchange_market(monkeypatch):
    state = {"futures": [listing("BTC", contract="PERPETUAL"), listing("QQQ"),
                          listing("UNITREE"), listing("XAU"),
                          listing("DELIVERY", contract="CURRENT_QUARTER"),
                          listing("PAUSED", status="HALT"), listing("OTHERQUOTE", quote="USDC")],
             "calls": Counter(), "gate": None, "started": asyncio.Event(), "fail": False}

    async def respond(request):
        state["calls"][(request.url.host, request.url.path)] += 1
        futures = request.url.host == "fapi.binance.com"
        if request.url.path.endswith("exchangeInfo"):
            if futures:
                state["started"].set()
                if state["gate"] is not None:
                    await state["gate"].wait()
                if state["fail"]:
                    raise httpx.ReadTimeout("catalog temporarily unavailable", request=request)
            return httpx.Response(200, json={"symbols": state["futures"] if futures else [listing("BTC")]})
        if request.url.path.endswith("klines"):
            return httpx.Response(200, json=[
                [stamp, "100", "103", "99", "101", "10", stamp + 59999, "0", 1, "0", "0", "0"]
                for stamp in (0, 60000)
            ])
        if request.url.path.endswith("ticker/24hr"):
            bases = state["futures"] if futures else [listing("BTC")]
            return httpx.Response(200, json=[{"symbol": row["symbol"], "lastPrice": "101",
                "priceChange": "1", "priceChangePercent": "1", "closeTime": 120000} for row in bases])
        raise AssertionError(f"Unexpected exchange endpoint: {request.url}")

    clients = [BinanceApiSupport(base_url=url, cache_namespace="discovery-test")
               for url in ("https://api.binance.com", "https://fapi.binance.com")]
    for client in clients:
        client.max_retries = 1
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    store = SimpleNamespace(save_items=lambda **kwargs: None, list_items=lambda **kwargs: [])
    market = ChartWorkspaceMarket(SimpleNamespace(
        spot=BinanceSpotMarketService(clients[0], research_store=store),
        usdm=BinanceUsdmMarketService(clients[1], research_store=store)), None)

    async def okx(*args):
        return {"tickSz": "0.01", "lotSz": "1"}

    monkeypatch.setattr(market.http, "okx_symbol", okx)
    monkeypatch.setattr("app.services.chart_workspace_market.settings.PUBLIC_SITE", False)
    try:
        yield market, state
    finally:
        await market.close()
        await asyncio.gather(*(client.aclose() for client in clients))


@pytest.mark.asyncio
async def test_catalog_discovers_crypto_and_tradfi_without_a_symbol_allowlist(exchange_market):
    market, _ = exchange_market
    catalog = {item.id: item for item in await market.symbols(wait_for_refresh=True)}
    assert {"binance:spot:BTCUSDT", "binance:usdm:BTCUSDT", "binance:usdm:QQQUSDT",
            "binance:usdm:UNITREEUSDT", "binance:usdm:XAUUSDT"} <= catalog.keys()
    assert not any(base in item.symbol for base in ("DELIVERY", "PAUSED", "OTHERQUOTE") for item in catalog.values())
    assert catalog["binance:usdm:QQQUSDT"].metadata["mincontract"] == 0.01


@pytest.mark.asyncio
async def test_new_listing_appears_after_expiry_and_failed_refresh_retains_the_last_catalog(exchange_market):
    market, state = exchange_market
    await market.symbols(wait_for_refresh=True)
    endpoint = ("fapi.binance.com", "/fapi/v1/exchangeInfo")
    state["futures"].append(listing("NEWLISTING"))
    assert "binance:usdm:NEWLISTINGUSDT" not in {s.id for s in await market.symbols(wait_for_refresh=True)}
    assert state["calls"][endpoint] == 1
    market._catalog_checked["binance:usdm"] = (time.time() - 601, True)
    refreshed = await market.symbols(wait_for_refresh=True)
    assert "binance:usdm:NEWLISTINGUSDT" in {s.id for s in refreshed}
    assert state["calls"][endpoint] == 2
    state["fail"] = True
    market._catalog_checked["binance:usdm"] = (0, True)
    assert {s.id for s in await market.symbols(wait_for_refresh=True)} == {s.id for s in refreshed}
    state["fail"] = False
    state["futures"] = [r for r in state["futures"] if r["baseAsset"] != "NEWLISTING"]
    market._catalog_checked["binance:usdm"] = (0, False)
    assert "binance:usdm:NEWLISTINGUSDT" not in {s.id for s in await market.symbols(wait_for_refresh=True)}


@pytest.mark.asyncio
async def test_completed_catalog_wait_is_shared_and_cancellation_keeps_exchange_refresh_alive(exchange_market):
    market, state = exchange_market
    state["gate"] = asyncio.Event()
    first = asyncio.create_task(market.symbols(wait_for_refresh=True))
    await asyncio.wait_for(state["started"].wait(), 1)
    second = asyncio.create_task(market.symbols(wait_for_refresh=True))
    await asyncio.sleep(0)
    assert not first.done() and not second.done()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not market._catalog_tasks["binance:usdm"].cancelled()
    state["gate"].set()
    catalog = await asyncio.wait_for(second, 1)
    assert "binance:usdm:QQQUSDT" in {s.id for s in catalog}
    assert state["calls"][("fapi.binance.com", "/fapi/v1/exchangeInfo")] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["binance:spot:BTCUSDT", "binance:usdm:BTCUSDT",
                                  "binance:usdm:QQQUSDT", "binance:usdm:UNITREEUSDT", "binance:usdm:XAUUSDT"])
async def test_discovered_products_load_history_replay_and_quotes_from_their_own_market(exchange_market, key):
    market, state = exchange_market
    await market.symbols(wait_for_refresh=True)
    history = await market.bars(key, "1m", limit=2, start=0, end=119999)
    assert [bar.time for bar in history.bars] == [0, 60000]
    assert all(bar.closed and bar.high == 103 and bar.volume == 10 for bar in history.bars)
    replay = await market.replay_bars(key, "1m", 2, 0, 120000)
    assert replay.bars == history.bars
    quote = (await market.quotes([key]))[0]
    assert quote.error is None and quote.price == 101 and quote.change_pct == 1
    spot = ":spot:" in key
    host, prefix = ("api.binance.com", "/api/v3") if spot else ("fapi.binance.com", "/fapi/v1")
    assert state["calls"][(host, prefix + "/klines")] == 2
    assert state["calls"][(host, prefix + "/ticker/24hr")] == 1
    if not spot:
        assert market._storage_symbol(history.symbol) == key


@pytest.mark.asyncio
async def test_discovered_tradfi_product_receives_native_futures_kline_updates(exchange_market, monkeypatch):
    market, _ = exchange_market
    await market.symbols(wait_for_refresh=True)
    urls = []

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def recv(self):
            await asyncio.sleep(0)
            return json.dumps({"E": 60001, "k": {"t": 60000, "T": 119999, "o": "101",
                "h": "104", "l": "100", "c": "102", "v": "11", "x": False}})

    def websocket(url):
        urls.append(url)
        return Stream()

    monkeypatch.setattr(market.http, "websocket", websocket)
    queue = asyncio.Queue()
    key = "binance:usdm:QQQUSDT"
    market.subscribe(key, "1m", queue)
    try:
        while True:
            event = await asyncio.wait_for(queue.get(), 1)
            if event["type"] == "bar" and event.get("live"):
                break
        assert event["symbol"] == key and event["bar"]["close"] == 102
        assert event["bar"]["closed"] is False and event["observed_at"] == 60001
        assert urls == ["wss://fstream.binance.com/market/ws/qqqusdt@kline_1m"]
    finally:
        market.unsubscribe(key, "1m", queue)


def test_catalog_endpoint_passes_the_optional_completed_refresh_wait():
    waits = []

    class Market:
        async def symbols(self, *, wait_for_refresh=False):
            waits.append(wait_for_refresh)
            return []

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[services] = lambda: SimpleNamespace(market=Market())
    with TestClient(application) as client:
        assert client.get("/chart-workspace/symbols").json() == []
        assert client.get("/chart-workspace/symbols?wait=true").json() == []
    assert waits == [False, True]
