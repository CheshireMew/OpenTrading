import asyncio
import base64
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.infra.market_data.symbol_icons import ASSET_INDEX_URL, IMAGE_TTL, INDEX_TTL, SymbolIconClient
from app.routers.chart_workspace import router, services

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvk0AAAAASUVORK5CYII=")
ICON = "https://bin.bnbstatic.com/image/new-asset.png"


@pytest.mark.asyncio
async def test_icons_discover_new_assets_automatically_and_share_concurrent_downloads():
    calls = []
    async def respond(request):
        calls.append(str(request.url))
        await asyncio.sleep(0)
        if str(request.url) == ASSET_INDEX_URL:
            return httpx.Response(200, json={"code": "000000", "data": [{"assetCode": "NEWASSET", "logoUrl": ICON}]})
        assert str(request.url) == ICON
        return httpx.Response(200, content=PNG)
    client = SymbolIconClient(httpx.MockTransport(respond))
    try:
        icons = await asyncio.gather(*(client.get("NEWASSET") for _ in range(8)))
        assert all(icon.content == PNG and icon.media_type == "image/png" for icon in icons)
        assert calls == [ASSET_INDEX_URL, ICON]
        assert (await client.get("NEWASSET")) == icons[0]
        assert len(calls) == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_unknown_asset_refreshes_catalog_without_waiting_six_hours():
    now, indexes = [1000], []
    def respond(request):
        if str(request.url) == ASSET_INDEX_URL:
            indexes.append(1)
            assets = ["FIRST"] if len(indexes) == 1 else ["FIRST", "NEW"]
            return httpx.Response(200, json={"code": "000000", "data": [{"assetCode": a, "logoUrl": ICON} for a in assets]})
        return httpx.Response(200, content=PNG)
    client = SymbolIconClient(httpx.MockTransport(respond), clock=lambda: now[0])
    try:
        assert await client.get("FIRST")
        now[0] += 61
        assert await client.get("NEW")
        assert len(indexes) == 2
        assert client.index["NEW"] == ICON
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_icon_refresh_preserves_stale_images_on_upstream_failure_and_recovers():
    now, broken = [1000], [False]
    def respond(request):
        if broken[0]:
            return httpx.Response(503)
        if str(request.url) == ASSET_INDEX_URL:
            return httpx.Response(200, json={"code": "000000", "data": [{"assetCode": "BTC", "logoUrl": ICON}]})
        return httpx.Response(200, content=PNG)
    client = SymbolIconClient(httpx.MockTransport(respond), clock=lambda: now[0])
    try:
        original = await client.get("BTC")
        now[0] += IMAGE_TTL + INDEX_TTL
        broken[0] = True
        assert await client.get("BTC") == original
        assert client.index["BTC"] == ICON
        broken[0] = False
        now[0] += 61
        assert await client.get("BTC") == original
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_missing_icons_use_binance_static_fallback_and_cache_misses():
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if str(request.url) == ASSET_INDEX_URL:
            return httpx.Response(503)
        if request.url.path.endswith("SOL.png"):
            return httpx.Response(200, content=PNG)
        return httpx.Response(200, text="not an image")
    client = SymbolIconClient(httpx.MockTransport(respond))
    try:
        assert (await client.get("SOL")).content == PNG
        assert await client.get("MISSING") is None
        count = len(calls)
        assert await client.get("MISSING") is None
        assert len(calls) == count
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_exact_asset_precedes_contract_multiplier_alias_and_cache_has_a_bound():
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if str(request.url) == ASSET_INDEX_URL:
            return httpx.Response(200, json={"code": "000000", "data": [
                {"assetCode": "PEPE", "logoUrl": ICON},
                {"assetCode": "1000SATS", "logoUrl": "https://bin.bnbstatic.com/image/sats.png"},
                {"assetCode": "SATS", "logoUrl": "https://bin.bnbstatic.com/image/wrong.png"}]})
        return httpx.Response(200, content=PNG)
    client = SymbolIconClient(httpx.MockTransport(respond))
    try:
        assert await client.get("1000PEPE")
        assert calls[-1] == ICON
        assert await client.get("1000SATS")
        assert calls[-1].endswith("sats.png")
        for i in range(520):
            client.remember(str(i), None)
        assert len(client.cache) == 512
        assert client.cache_bytes == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_icon_route_serves_same_origin_images_browser_cache_and_etags():
    def respond(request):
        if str(request.url) == ASSET_INDEX_URL:
            return httpx.Response(200, json={"code": "000000", "data": [{"assetCode": "NEW", "logoUrl": ICON}]})
        return httpx.Response(200, content=PNG) if str(request.url) == ICON else httpx.Response(404)
    icons = SymbolIconClient(httpx.MockTransport(respond))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[services] = lambda: SimpleNamespace(market=SimpleNamespace(icons=icons))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/chart-workspace/symbol-icons/NEW")
            assert response.content == PNG
            assert response.headers["content-type"] == "image/png"
            assert "max-age=86400" in response.headers["cache-control"]
            cached = await client.get("/chart-workspace/symbol-icons/NEW", headers={"If-None-Match": response.headers["etag"]})
            assert cached.status_code == 304 and not cached.content
            assert (await client.get("/chart-workspace/symbol-icons/MISSING")).status_code == 404
            assert (await client.get("/chart-workspace/symbol-icons/bad%20asset")).status_code == 422
    finally:
        await icons.aclose()
