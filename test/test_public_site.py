"""The anonymous deployment must not expose the local application's powers."""
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from config import settings


@pytest.fixture
def public_app(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SITE", True)
    return create_app("api")


@pytest.mark.asyncio
async def test_public_site_rejects_private_endpoints_even_with_loopback_forwarding(public_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="https://trade.blacknico.com") as client:
        for method, path in [
            ("GET", "/api/v1/llm-config"), ("PUT", "/api/v1/llm-config"),
            ("GET", "/api/v1/research/workbench"), ("GET", "/api/v1/research/events"),
            ("POST", "/api/v1/research/alerts"), ("POST", "/api/v1/research/alerts/evaluate"),
            ("GET", "/api/v1/research/signals"), ("GET", "/api/v1/research/screeners"),
            ("GET", "/api/v1/chart-workspace/scripts"), ("PUT", "/api/v1/chart-workspace/scripts/attacker"),
            ("GET", "/api/v1/chart-workspace/pine-runs"), ("POST", "/api/v1/chart-workspace/pine-runs"),
            ("POST", "/api/v1/data-health/repair"), ("POST", "/api/v1/signal-lab/liquidity/refresh"),
            ("GET", "/docs"), ("GET", "/openapi.json"),
        ]:
            result = await client.request(method, path, headers={"X-Forwarded-For": "127.0.0.1"}, json={})
            assert result.status_code in {404, 405}, (method, path, result.status_code)


@pytest.mark.asyncio
async def test_public_tools_pages_can_read_their_initial_configuration(public_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="https://trade.blacknico.com") as client:
        response = await client.get("/api/v1/tools/contract")
        assert response.status_code == 200
        contract = response.json()
        assert contract["dca_defaults"]["symbol"] == "BTC/USDT"
        assert "standard" in contract["dca_strategies"]
        assert contract["compare_defaults"]["symbol_a"] == "BTC"
        assert contract["compare_defaults"]["symbol_b"] == "ETH"
        assert contract["dca_max_days"] > 0


@pytest.mark.asyncio
async def test_public_defaults_are_code_defaults_without_personal_repository_access(public_app):
    public_app.state.runtime_services = SimpleNamespace(require_api=lambda: pytest.fail("Defaults must not read personal storage"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="https://trade.blacknico.com") as client:
        scripts = (await client.get("/api/v1/chart-workspace/defaults/scripts")).json()
        assert len(scripts) == 2 and all(row["readonly"] for row in scripts)
        assert all("source" in row["data"] for row in scripts)
        assert (await client.get("/api/v1/chart-workspace/defaults/layouts")).json() == []
        assert (await client.get("/api/v1/chart-workspace/defaults/watchlists")).json()[0]["id"] == "default"


@pytest.mark.asyncio
async def test_public_limits_actual_body_and_rejects_arbitrary_hosts(public_app):
    async def chunks():
        for _ in range(9):
            yield b"x" * 8192

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="https://trade.blacknico.com") as client:
        assert (await client.post("/api/v1/tools/dca_simulate", content=chunks())).status_code == 413
        assert (await client.get("/api/v1/chart-workspace/defaults/scripts?" + "q=" + "x" * 8193)).status_code == 413
        assert (await client.get("/", headers={"Host": "attacker.invalid"})).status_code == 400


def test_cross_site_websockets_are_rejected_before_runtime_access(public_app):
    client = TestClient(public_app, base_url="https://trade.blacknico.com")
    for origin in ("https://attacker.invalid", "null", "http://trade.blacknico.com"):
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect("wss://trade.blacknico.com/api/v1/chart-workspace/stream", headers={"Origin": origin}):
                pytest.fail("Cross-site websocket was accepted")
        assert error.value.code == 1008


@pytest.mark.asyncio
async def test_public_ai_factory_never_reads_credentials(monkeypatch):
    from app.infra.llm_client import LLMClientFactory

    monkeypatch.setattr(settings, "PUBLIC_SITE", True)
    config = SimpleNamespace(read_effective_config=lambda: pytest.fail("Public mode must never read model credentials"))
    factory = LLMClientFactory(config)
    try:
        assert factory() is None
    finally:
        await factory.aclose()


@pytest.mark.asyncio
async def test_public_quotes_reuse_the_shared_feed_and_bound_live_channels(monkeypatch):
    import asyncio
    from app.contracts.chart_workspace import ChartSymbol
    from app.services.chart_workspace_market import ChartWorkspaceMarket

    monkeypatch.setattr(settings, "PUBLIC_SITE", True)

    async def snapshot():
        return {"spot_ticker": {"items": [{"symbol": "BTCUSDT", "last_price": 100,
            "price_change": 5, "price_change_pct": 5.2, "close_time": 12345}]}}

    market = ChartWorkspaceMarket(SimpleNamespace(snapshot_service=SimpleNamespace(get_market_page_snapshot_data=snapshot)), None)
    info = ChartSymbol(id="binance:spot:BTCUSDT", symbol="BTCUSDT", name="BTC/USDT", exchange="binance",
        market="spot", currency="USDT", timeframes=["1m"])
    market.catalog[info.id] = info

    async def symbols():
        return [info]

    async def pump(*args):
        await asyncio.Event().wait()

    market.symbols, market._pump = symbols, pump
    try:
        quote = (await market.quotes([info.id]))[0]
        assert quote.price == 100 and quote.updated_at == 12345 and quote.error is None
        for index in range(32):
            market.subscribe(str(index), "1m", asyncio.Queue())
        market.subscribe("0", "1m", asyncio.Queue())
        with pytest.raises(ValueError, match="实时行情连接已满"):
            market.subscribe("33", "1m", asyncio.Queue())
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_public_asset_response_does_not_read_research_or_signals(monkeypatch):
    from app.services.asset_research_service import AssetResearchService

    monkeypatch.setattr(settings, "PUBLIC_SITE", True)
    private = SimpleNamespace(get_workbench=lambda **_: pytest.fail("Private research was read"),
        list_signals=lambda **_: pytest.fail("Private signals were read"))
    service = AssetResearchService(research_repository=private, signal_repository=private,
        market_query_service=None, index_data_service=None, binance_market_service=None,
        binance_web3_heat_rank_service=None, binance_web3_token_service=None, pair_compare_service=None)

    async def market(*args):
        return {"currentPrice": 100, "indicators": None, "history": [], "marketContext": {}, "issues": []}

    service._load_market = market
    result = await service.get_asset(symbol="BTC/USDT", timeframe="1h", history_days=30)
    assert result.currentPrice == 100
    assert result.watchItems == result.notes == result.alerts == result.events == result.signals == []
