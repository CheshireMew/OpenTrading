from __future__ import annotations

import asyncio
from collections import Counter
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI

from app.dependencies import get_equity_catalog_service
from app.routers.market.equity_catalog import router
from app.services.market.equity_catalog_normalizers import canonical_ticker, equity_referral_url, make_listing, merge_listings
from app.services.market.equity_catalog_service import EquityCatalogService


def payload_for(request: httpx.Request):
    path = request.url.path
    if path.endswith("get-exchange-info"):
        return {"code": "000000", "data": {"syms": [
            *[{"s": f"STOCK{i}", "tr": "BUY_SELL"} for i in range(600)],
            {"s": "AAPL", "tr": "BUY_SELL"}, {"s": "MU", "tr": "BUY_SELL"},
            {"s": "GLD", "tr": "BUY_SELL"}, {"s": "OLD", "tr": "OFFMARKET"},
        ]}}
    if path.endswith("get-symbols-static"):
        return {"data": [
            {"s": "AAPL", "n": "Apple Inc.", "t": "STOCK", "l": "AAPL-custom.png"},
            {"s": "MU", "n": "Micron Technology", "t": "STOCK"},
            {"s": "GLD", "n": "SPDR Gold Shares", "t": "ETF"},
        ]}
    if path.endswith("get-products"):
        return {"data": [
            {"s": "MUBUSDT", "b": "MUB", "q": "USDT", "an": "Micron (bStocks)", "st": "TRADING", "tags": ["bStocks"]},
            {"s": "BNBUSDT", "b": "BNB", "q": "USDT", "an": "BNB", "st": "TRADING", "tags": ["Layer1"]},
        ]}
    if path.endswith("alpha/all/token/list"):
        return {"data": [
            {"symbol": "AAPLon", "name": "Apple (Ondo)", "stockState": True, "chainId": "56",
             "iconUrl": "https://bin.bnbstatic.com/token/apple-ondo.png",
             "contractAddress": "0xapple", "rwaInfo": {"metaInfo": {"ticker": "AAPL"}}},
            {"symbol": "ONDO", "name": "Ondo", "stockState": False},
            {"symbol": "OLDOn", "stockState": True, "offline": True},
        ]}
    if path == "/fapi/v1/exchangeInfo":
        return {"symbols": [
            {"symbol": "AAPLUSDT", "baseAsset": "AAPL", "quoteAsset": "USDT", "status": "TRADING", "contractType": "TRADIFI_PERPETUAL", "underlyingType": "EQUITY"},
            {"symbol": "ONLYUSDT", "baseAsset": "ONLY", "quoteAsset": "USDT", "status": "TRADING", "contractType": "TRADIFI_PERPETUAL", "underlyingType": "EQUITY"},
            {"symbol": "XAUUSDT", "baseAsset": "XAU", "underlyingType": "COMMODITY"},
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "underlyingType": "COIN"},
        ]}
    if path == "/api/v5/public/instruments":
        if request.url.params["instType"] == "SPOT":
            return {"code": "0", "data": [
                {"instId": "XAAPL-USDT", "baseCcy": "XAAPL", "quoteCcy": "USDT", "instCategory": "3", "state": "live"},
                {"instId": "XAAPL-USDC", "baseCcy": "XAAPL", "quoteCcy": "USDC", "instCategory": "3", "state": "live"},
                {"instId": "XTESTA-USDT", "baseCcy": "XTESTA", "quoteCcy": "USDT", "instCategory": "3", "state": "live"},
                {"instId": "XRP-USDT", "baseCcy": "XRP", "instCategory": "1", "state": "live"},
            ]}
        return {"data": [{"instId": "AAPL-USDT-SWAP", "ctValCcy": "AAPL", "settleCcy": "USDT", "instCategory": "3", "state": "live"}]}
    if path == "/api/v3/market/instruments":
        if request.url.params["category"] == "SPOT":
            return {"code": "00000", "data": [
                {"symbol": "RAAPLUSDT", "baseCoin": "rAAPL", "quoteCoin": "USDT", "symbolType": "stock", "isReality": "yes", "fullName": "Apple", "instrumentType": "stock", "status": "online"},
                {"symbol": "RSOXLUSDT", "baseCoin": "rSOXL", "quoteCoin": "USDT", "symbolType": "stock", "isReality": "yes", "fullName": "Semiconductor Bull 3X ETF", "instrumentType": "etf", "status": "online"},
                {"symbol": "BTCUSDT", "baseCoin": "BTC", "symbolType": "crypto", "isReality": "no", "status": "online"},
            ]}
        if request.url.params["category"] != "USDT-FUTURES":
            return {"code": "00000", "data": []}
        return {"code": "00000", "data": [
            {"symbol": "AAPLUSDT", "baseCoin": "AAPL", "quoteCoin": "USDT", "symbolType": "stock", "type": "perpetual", "fullName": "Apple", "instrumentType": "stock", "status": "online"},
            {"symbol": "DELIVERYUSDT", "baseCoin": "DELIVERY", "symbolType": "stock", "type": "delivery", "status": "online"},
        ]}
    raise AssertionError(f"Unexpected URL: {request.url}")


@pytest.mark.asyncio
async def test_complete_source_catalogs_merge_without_truncating_or_crypto():
    service = EquityCatalogService(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload_for(request))))
    try:
        catalog = await service.get_catalog()
    finally:
        await service.aclose()
    by_ticker = {item.ticker: item for item in catalog.items}
    assert len(by_ticker) == 604
    assert by_ticker["AAPL"].platforms == ["binance", "bitget", "okx"]
    assert by_ticker["AAPL"].trading_types == ["perpetual", "spot"]
    assert len(by_ticker["AAPL"].offerings) == 8
    assert by_ticker["AAPL"].name == "Apple Inc."
    assert by_ticker["AAPL"].logo_url == "https://bin.bnbstatic.com/static/stock/AAPL-custom.png"
    assert by_ticker["MU"].logo_url is None
    assert by_ticker["MU"].offerings[-1].symbol == "MUBUSDT"
    assert by_ticker["ONLY"].trading_types == ["perpetual"]
    assert by_ticker["SOXL"].asset_type == "etf"
    assert not {"BTC", "BNB", "ONDO", "XAU", "XRP", "TESTA", "GLD", "OLD", "DELIVERY"} & by_ticker.keys()
    statuses = {source.id: source for source in catalog.sources}
    assert statuses["binance_stocks"].count == 602
    assert statuses["okx_spot"].count == 1  # USDT / USDC are one underlying.
    assert statuses["bitget_stockplus"].error == "catalog_not_verified"
    assert catalog.complete is False  # Never claim coverage of an unavailable product.
    referral_parameters = {
        "binance": ("ref", "SRXT5KUM"),
        "okx": ("channelId", "A999998"),
        "bitget": ("clacCode", "W76TDL38"),
    }
    for item in catalog.items:
        for offering in item.offerings:
            key, code = referral_parameters[offering.platform]
            assert parse_qs(urlsplit(offering.url).query)[key] == [code]
    for source in catalog.sources:
        if source.trading_type == "perpetual":  # These source links show raw API catalogs.
            assert not {"ref", "channelId", "clacCode"} & parse_qs(urlsplit(source.url).query).keys()
        else:
            key, code = referral_parameters[source.platform]
            assert parse_qs(urlsplit(source.url).query)[key] == [code]


def test_invitation_links_preserve_stock_destination_and_do_not_change_api_urls():
    original = "https://www.okx.com/trade-spot/xaapl-usdt?channelid=old&lang=zh-CN&empty=#workspaceId=-2"
    expected = "https://www.okx.com/trade-spot/xaapl-usdt?lang=zh-CN&empty=&channelId=A999998#workspaceId=-2"
    assert equity_referral_url(original) == expected
    assert equity_referral_url(expected) == expected
    for url in (
        "https://www.okx.com/api/v5/public/instruments?instType=SWAP",
        "https://www.binance.com/bapi/equity/v2/public/equity/symbol/get-exchange-info",
        "https://fapi.binance.com/fapi/v1/exchangeInfo",
        "https://api.bitget.com/api/v3/market/instruments?category=SPOT",
        "https://example.com/stock/AAPL",
        "",
    ):
        assert equity_referral_url(url) == url


@pytest.mark.asyncio
async def test_failed_source_keeps_previous_support_and_recovers():
    fail = False

    def handler(request):
        if fail and request.url.path == "/api/v5/public/instruments":
            return httpx.Response(503)
        return httpx.Response(200, json=payload_for(request))

    service = EquityCatalogService(transport=httpx.MockTransport(handler))
    try:
        first = await service.get_catalog()
        fail = True
        second = await service.get_catalog(refresh=True)
        source = next(s for s in second.sources if s.id == "okx_spot")
        assert source.status == "stale"
        assert source.updated_at == next(s for s in first.sources if s.id == "okx_spot").updated_at
        assert "okx" in next(i for i in second.items if i.ticker == "AAPL").platforms
        fail = False
        third = await service.get_catalog(refresh=True)
        assert next(s for s in third.sources if s.id == "okx_spot").status == "ok"
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_unavailable_catalog_is_not_reported_as_confirmed_empty():
    def handler(request):
        if request.url.path == "/api/v5/public/instruments":
            return httpx.Response(200, json={"code": "0", "data": {"unexpected": []}})
        return httpx.Response(200, json=payload_for(request))

    service = EquityCatalogService(transport=httpx.MockTransport(handler))
    try:
        catalog = await service.get_catalog()
        assert {s.status for s in catalog.sources if s.platform == "okx"} == {"unavailable"}
        assert "okx" not in next(i for i in catalog.items if i.ticker == "AAPL").platforms
        assert catalog.complete is False
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_concurrent_refreshes_share_requests_and_normal_reads_use_cache():
    calls = Counter()

    async def handler(request):
        calls[str(request.url)] += 1
        await asyncio.sleep(0)
        return httpx.Response(200, json=payload_for(request))

    service = EquityCatalogService(transport=httpx.MockTransport(handler))
    try:
        catalogs = await asyncio.gather(*(service.get_catalog(refresh=True) for _ in range(4)))
        assert all(result is catalogs[0] for result in catalogs)
        await service.get_catalog()
        assert set(calls.values()) == {1}
    finally:
        await service.aclose()


def test_share_classes_and_leveraged_funds_keep_distinct_underlyings():
    listings = []
    for ticker, platform in [("BRKB", "okx"), ("BRK-B", "binance"), ("BRK.A", "binance"), ("NVDA", "okx"), ("NVDL", "bitget")]:
        listings.append(make_listing(ticker=ticker, name=ticker, platform=platform, trading_type="spot", product="Stocks",
                                     symbol=ticker, quote_currency="USD", source_id=platform, url="https://example.com"))
    metadata = [
        {"ticker": "BRK-B", "name": "Berkshire Hathaway", "asset_type": "stock"},
        {"ticker": "BRKB", "logo_url": "https://example.com/berkshire.png"},
    ]
    items = {item.ticker: item for item in merge_listings(listings, metadata)}
    assert set(items) == {"BRK.B", "BRK.A", "NVDA", "NVDL"}
    assert items["BRK.B"].platforms == ["binance", "okx"]
    assert items["BRK.B"].logo_url == "https://example.com/berkshire.png"
    assert items["BRK.A"].logo_url is None
    assert canonical_ticker("PAYP") != canonical_ticker("PYPL")
    assert canonical_ticker("SKHYNIX") != canonical_ticker("SKHY")
    assert canonical_ticker("STXX") != canonical_ticker("STX")


@pytest.mark.asyncio
async def test_exchange_specific_crypto_collisions_do_not_merge_unrelated_equities():
    def handler(request):
        return httpx.Response(200, json={"symbols": [
            {"symbol": f"{base}USDT", "baseAsset": base, "quoteAsset": "USDT", "status": "TRADING",
             "underlyingType": "EQUITY", "contractType": "TRADIFI_PERPETUAL"}
            for base in ["PAYP", "PYPL", "STXX", "BBX", "USDEX"]
        ]})
    service = EquityCatalogService(transport=httpx.MockTransport(handler))
    try:
        listings, _ = await service._load_binance_perpetual()
        assert {row["ticker"] for row in listings} == {"PAYP", "PYPL", "STX", "BB", "USDE"}
        assert next(row for row in listings if row["ticker"] == "USDE")["asset_type"] != "index"
    finally:
        await service.aclose()


@pytest.mark.asyncio
async def test_http_route_uses_catalog_contract_and_refresh_query():
    service = EquityCatalogService(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload_for(request))))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_equity_catalog_service] = lambda: service
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/equities/catalog?refresh=true")
            assert response.status_code == 200
            assert len(response.json()["items"]) == 604
            assert next(item for item in response.json()["items"] if item["ticker"] == "AAPL")["logo_url"] == "https://bin.bnbstatic.com/static/stock/AAPL-custom.png"
            invalid = await client.get("/api/v1/equities/catalog?refresh=invalid")
            assert invalid.status_code == 422
    finally:
        await service.aclose()
