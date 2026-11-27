"""On-chain charts keep source, chain, address, history and live updates distinct."""
from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from types import SimpleNamespace

import pytest
import pytest_asyncio
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.market.web3_chains import web3_storage_symbol
from app.infra.persistence.market.kline_store import KlineStore
from app.infra.cache import CacheService
from app.infra.market_data.onchain import OnchainMarketClient
from app.routers.chart_workspace import router, services
from app.services.chart_onchain_market import ChartOnchainMarket
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.services.market.binance_web3_tokens import BinanceWeb3TokenService

ADDRESS = "0x" + "ab" * 20
OUTSIDE = "0x" + "cd" * 20
SOLANA = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class PublicMarkets:
    def __init__(self):
        self.tokens = [
            dict(symbol="NVDAon", name="NVIDIA (Ondo)", alphaId="ALPHA_1", chainId="56", contractAddress=ADDRESS),
            dict(symbol="SAME", name="Ethereum token", alphaId="ALPHA_2", chainId="1", contractAddress=ADDRESS),
            dict(symbol="USDC", name="USD Coin", chainId="CT_501", contractAddress=SOLANA),
            dict(symbol="OFFLINE", alphaId="ALPHA_3", chainId="56", contractAddress=OUTSIDE, offline=True),
        ]
        self.calls = Counter()
        self.history_calls = []
        self.rows = [[0, 100, 103, 99, 101, 10], [60000, 100, 103, 99, 101, 10]]
        self.fail = False
        self.gate = None
        self.started = asyncio.Event()
        self.closed = False

    async def token_list(self):
        self.calls["catalog"] += 1
        if self.fail:
            raise RuntimeError("source unavailable")
        return self.tokens

    async def alpha_markets(self):
        return [dict(symbol=token['alphaId'] + 'USDT', baseAsset=token['alphaId'], quoteAsset="USDT",
            status="TRADING", filters=[{"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                       {"filterType": "LOT_SIZE", "stepSize": "0.0001"}]) for token in self.tokens if token.get('alphaId')]

    async def alpha_history(self, symbol, timeframe, limit, start, end):
        self.history_calls.append(("alpha", symbol, timeframe, start, end))
        return [row + [row[0] + 59999] for row in self.rows
                if row[0] <= end and (start is None or row[0] >= start)][:limit]

    async def web3_history(self, address, platform, timeframe, limit, start, end):
        self.history_calls.append((platform, address, timeframe, start, end))
        rows = [[row[1] + 100, row[2] + 100, row[3] + 100, row[4] + 100, row[5], row[0], 1]
                for row in self.rows if row[0] <= end and (start is None or row[0] >= start)]
        return rows[-limit:] if start is None else rows[:limit]

    async def alpha_ticker(self, symbol):
        return {"lastPrice": "101", "priceChange": "1", "priceChangePercent": "1", "closeTime": 120000}

    async def web3_dynamic(self, chain, address):
        self.calls[(chain, address)] += 1
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("source unavailable")
        if address == OUTSIDE and chain != "56":
            return {}
        return {"price": "201", "percentChange24h": "0.5"}

    async def aclose(self):
        self.closed = True


@pytest_asyncio.fixture
async def chain_market(installed_database_runtime, monkeypatch):
    client = PublicMarkets()
    source = ChartOnchainMarket(client)
    store = KlineStore(database_runtime=installed_database_runtime)
    market = ChartWorkspaceMarket(None, None, onchain=source, kline_store=store)
    for venue in ("binance:spot", "binance:usdm", "okx:spot"):
        market._catalog_checked[venue] = (time.time(), True)
    monkeypatch.setattr("app.services.chart_workspace_market.settings.PUBLIC_SITE", False)
    try:
        yield market, source, client, store
    finally:
        await market.close()
        assert client.closed


@pytest.mark.asyncio
async def test_catalog_automatically_discovers_alpha_and_each_supported_chain(chain_market):
    market, _, client, _ = chain_market
    catalog = {item.id: item for item in await market.symbols(wait_for_refresh=True)}
    assert {"binance:alpha:ALPHA_1USDT", "binance:alpha:ALPHA_2USDT",
            f"web3:bsc:{ADDRESS}", f"web3:ethereum:{ADDRESS}", f"web3:solana:{SOLANA}"} <= catalog.keys()
    assert not any("OFFLINE" in item.name for item in catalog.values())
    assert catalog["binance:alpha:ALPHA_1USDT"].name == "NVDAon/USDT"
    assert catalog[f"web3:bsc:{ADDRESS}"].name == "NVDAon/USD"
    assert catalog[f"web3:solana:{SOLANA}"].symbol == SOLANA
    client.tokens.append(dict(symbol="NEW", alphaId="ALPHA_4", chainId="8453", contractAddress=OUTSIDE))
    market._catalog_checked["web3"] = (0, True)
    market._catalog_checked["binance:alpha"] = (0, True)
    refreshed = {item.id for item in await market.symbols(wait_for_refresh=True)}
    assert {f"web3:base:{OUTSIDE}", "binance:alpha:ALPHA_4USDT"} <= refreshed
    client.fail = True
    market._catalog_checked["web3"] = (0, True)
    assert f"web3:base:{OUTSIDE}" in {item.id for item in await market.symbols(wait_for_refresh=True)}


@pytest.mark.asyncio
async def test_source_prices_and_persisted_history_never_mix(chain_market):
    market, source, _, store = chain_market
    await market.symbols(wait_for_refresh=True)
    keys = ["binance:alpha:ALPHA_1USDT", f"web3:bsc:{ADDRESS}", f"web3:ethereum:{ADDRESS}"]
    data = [await market.bars(key, "1m", 2, 0, 119999) for key in keys]
    assert [item.bars[0].close for item in data] == [101, 201, 201]
    assert [item.source for item in data] == ["binance-alpha", "binance-web3", "binance-web3"]
    assert [item.symbol.currency for item in data] == ["USDT", "USD", "USD"]
    stored = [market._storage_symbol(item.symbol) for item in data]
    assert len(set(stored)) == 3
    assert [store.get_before(key, "1m", 120000, 2)[0][4] for key in stored] == [101, 201, 201]
    replay = await market.replay_bars(keys[1], "1m", 2, 0, 120000)
    assert replay.bars == data[1].bars
    quotes = await market.quotes(keys)
    assert [quote.price for quote in quotes] == [101, 201, 201]
    assert all(quote.error is None for quote in quotes)
    assert source.stream_url(data[1].symbol, "30m") is None


@pytest.mark.asyncio
async def test_sparse_chain_history_uses_actual_records_without_assuming_cached_gaps_are_complete(chain_market):
    market, _, client, store = chain_market
    await market.symbols(wait_for_refresh=True)
    key = f"web3:bsc:{ADDRESS}"
    # Both trades are much older than a two-minute clock window.
    data = await market.bars(key, "1m", 2)
    assert [row.time for row in data.bars] == [0, 60000]
    client.rows.append([120000, 100, 103, 99, 101, 10])
    repeated = await market.bars(key, "1m", 2, end=179999)
    assert [bar.time for bar in repeated.bars] == [60000, 120000]
    now = int(time.time() * 1000)
    opening = now // 60000 * 60000
    client.rows = [client.rows[-1], [opening, 100, 103, 99, 101, 10]]
    live = await market.bars(key, "1m", 2)
    assert live.bars[-1].closed is False
    assert opening not in [row[0] for row in store.get_before(market._storage_symbol(live.symbol), "1m", now + 1, 10)]


@pytest.mark.asyncio
async def test_forward_chain_history_bounds_the_requested_page(chain_market):
    market, source, client, _ = chain_market
    await market.symbols(wait_for_refresh=True)
    info = await market.resolve(f"web3:bsc:{ADDRESS}")
    await source.history(info, "1m", 2, 0, 9_999_999)
    assert client.history_calls[-1][-2:] == (0, 119999)


@pytest.mark.asyncio
async def test_address_search_resolves_outside_alpha_and_saved_identity_survives_refresh(chain_market):
    market, _, client, _ = chain_market
    await market.symbols(wait_for_refresh=True)
    found = await market.search_symbols(OUTSIDE)
    assert [item.id for item in found] == [f"web3:bsc:{OUTSIDE}"]
    assert (await market.resolve(found[0].id)).id == found[0].id
    market._catalog_checked["web3"] = (0, True)
    assert found[0].id in {item.id for item in await market.symbols(wait_for_refresh=True)}
    assert (await market.search_symbols("bsc:" + OUTSIDE))[0].id == found[0].id
    client.fail = True
    with pytest.raises(RuntimeError, match="暂时无法读取"):
        await market.search_symbols("0x" + "ef" * 20)
    with pytest.raises(ValueError, match="有效"):
        await market.search_symbols("not an address")


@pytest.mark.asyncio
async def test_concurrent_address_resolution_is_shared_and_one_cancellation_keeps_it_alive(chain_market):
    _, source, client, _ = chain_market
    client.gate = asyncio.Event()
    key = f"web3:bsc:{OUTSIDE}"
    first = asyncio.create_task(source.resolve_web3(key))
    await asyncio.wait_for(client.started.wait(), 1)
    second = asyncio.create_task(source.resolve_web3(key))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    client.gate.set()
    assert (await asyncio.wait_for(second, 1)).id == key
    assert client.calls[("56", OUTSIDE)] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["binance:alpha:ALPHA_1USDT", f"web3:solana:{SOLANA}"])
async def test_native_alpha_and_contract_streams_use_their_own_wire_formats(chain_market, monkeypatch, key):
    market, source, _, _ = chain_market
    await market.symbols(wait_for_refresh=True)
    info = await market.resolve(key)
    now = int(time.time() * 1000)
    opening = now // 60000 * 60000
    row = dict(o="201", h="203", l="199", c="202", v="10")
    if info.market == "alpha":
        row.update(t=opening, T=opening + 59999, x=False)
        payload = dict(E=now, k=row)
    else:
        row.update(ot=opening, ct=opening + 60000, i="1m")
        payload = dict(ca=SOLANA + "@CT_501", k=row)
    incoming, outgoing, urls, subscriptions = asyncio.Queue(), asyncio.Queue(), [], []
    incoming.put_nowait(json.dumps(payload))

    class Stream:
        async def send(self, value):
            subscriptions.append(json.loads(value))

        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def recv(self):
            return await incoming.get()

    def websocket(url):
        urls.append(url)
        return Stream()

    monkeypatch.setattr(market.http, "websocket", websocket)
    market.subscribe(key, "1m", outgoing)
    task = market.channels[(key, "1m")][0]
    try:
        while True:
            event = await asyncio.wait_for(outgoing.get(), 2)
            if event["type"] == "bar" and event.get("live"):
                break
        assert event["bar"]["close"] == 202 and event["bar"]["closeTime"] == opening + 60000
        assert event["bar"]["closed"] is False
        assert urls == [source.stream_url(info, "1m")]
        assert subscriptions == [{"method": "SUBSCRIBE", "params": [source.stream_name(info, "1m")], "id": 1}]
        if info.market == "web3":
            assert SOLANA + "@CT_501" in subscriptions[0]["params"][0]
    finally:
        market.unsubscribe(key, "1m", outgoing)
        await asyncio.gather(task, return_exceptions=True)


def test_solana_storage_and_legacy_web3_reader_preserve_address_case():
    assert web3_storage_symbol(SOLANA, "solana") != web3_storage_symbol(SOLANA.lower(), "solana")
    assert BinanceWeb3TokenService._storage_symbol(address=SOLANA, platform="solana").endswith(SOLANA)
    assert web3_storage_symbol(ADDRESS.upper().replace("0X", "0x"), "bsc") == web3_storage_symbol(ADDRESS, "bsc")


@pytest.mark.asyncio
async def test_chain_client_caches_exact_historical_pages_without_crossing_chains():
    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [[200, 203, 199, 201, 10, 0, 1]]})

    client = OnchainMarketClient(cache_service=CacheService())
    client.candles._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        first = await client.web3_history(ADDRESS, "bsc", "1m", 2, None, 119999)
        assert await client.web3_history(ADDRESS, "bsc", "1m", 2, None, 119999) == first
        assert len(calls) == 1
        await client.web3_history(ADDRESS, "base", "1m", 2, None, 119999)
        assert len(calls) == 2
        assert calls[0].url.params["interval"] == "1min"
    finally:
        await client.aclose()


def test_address_search_endpoint_returns_market_identity_and_reports_bad_queries():
    async def search(query):
        if query == "bad":
            raise ValueError("请输入有效的链上合约地址")
        return [ChartOnchainMarket._web3_symbol("bsc", ADDRESS)]
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[services] = lambda: SimpleNamespace(market=SimpleNamespace(search_symbols=search))
    with TestClient(app) as client:
        result = client.get("/chart-workspace/symbols/search", params={"query": ADDRESS})
        assert result.status_code == 200 and result.json()[0]["id"] == f"web3:bsc:{ADDRESS}"
        assert client.get("/chart-workspace/symbols/search?query=bad").status_code == 422
