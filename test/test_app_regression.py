from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Request

import app.lifecycle as lifecycle_module
import app.main as main_module
import app.web as web_module
import app.background_runtime as background_runtime_module
from app.exceptions import unhandled_exception_handler
from app.runtime import (
    AppRuntimeServices,
    BackgroundRuntimeServices,
    IndicatorRuntimeServices,
    InfraRuntimeServices,
)


@pytest.mark.asyncio
async def test_lifespan_monitors_and_stops_managers(monkeypatch):
    events: list[str] = []

    class FakeManager:
        async def start_active_run_monitoring(self):
            events.append("monitor")

        async def shutdown(self):
            events.append("shutdown")

    class FakeSchedulerRuntime:
        async def start(self, _owner_id=""):
            events.append("start_scheduler")

        async def shutdown(self):
            events.append("scheduler_shutdown")

    class FakeSnapshot:
        async def start(self, **kwargs):
            events.append("snapshot_start")

        async def shutdown(self):
            events.append("snapshot_shutdown")

    class FakeSpotMarket:
        async def get_ticker_24hr(self):
            return {}

    class FakeUsdmMarket:
        async def get_ticker_24hr(self):
            return {}

        async def get_mark_price(self):
            return {}

    class FakeBinanceMarket:
        spot = FakeSpotMarket()
        usdm = FakeUsdmMarket()

        def start(self):
            events.append("binance_market_start")

        async def shutdown(self):
            events.append("binance_market_shutdown")

    class FakeDatabaseRuntime:
        def dispose(self):
            events.append("dispose_db")

    monkeypatch.setattr(lifecycle_module, "_init_db", lambda *_args: events.append("init_db"))
    monkeypatch.setattr(
        lifecycle_module,
        "build_app_runtime_services",
        lambda _role=None: AppRuntimeServices(
            infra=InfraRuntimeServices(FakeDatabaseRuntime(), object()),
            indicators=IndicatorRuntimeServices(object(), object()),
            background=BackgroundRuntimeServices(FakeSchedulerRuntime()),
        ),
    )
    monkeypatch.setattr(
        background_runtime_module._ProcessFileLock, "acquire", lambda self: True
    )
    monkeypatch.setattr(
        background_runtime_module._ProcessFileLock, "release", lambda self: None
    )
    app = main_module.create_app(role="background")

    async with lifecycle_module.lifespan(app):
        events.append("inside")
        await app.state.background_services_task
        await app.state.background_runtime.wait_until_started()

    assert events[0] == "init_db"
    assert events.index("init_db") < events.index("inside")
    assert events.index("init_db") < events.index("start_scheduler")
    assert events[-2:] == [
        "scheduler_shutdown",
        "dispose_db",
    ]


def test_root_returns_frontend_boot_payload_when_build_missing(
    api_harness, monkeypatch
):
    monkeypatch.setattr(web_module, "FRONTEND_DIST_DIR", Path("Z:/missing"))
    monkeypatch.setattr(
        web_module, "FRONTEND_INDEX_FILE", Path("Z:/missing/index.html")
    )

    response = api_harness["client"].get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "OpenTrading API is running"
    assert response.json()["docs"] == "/docs"


def test_validation_errors_keep_the_string_error_contract(api_harness):
    response = api_harness["client"].post(
        "/api/v1/tools/dca_simulate",
        json={"amount": -1},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert "amount" in response.json()["detail"]


def test_root_and_spa_fallback_serve_built_frontend(api_harness, monkeypatch):
    dist_dir = web_module.BASE_DIR / "frontend" / "dist"
    assets_dir = dist_dir / "assets"
    dist_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    index_file = dist_dir / "index.html"
    asset_file = assets_dir / "app.js"
    original_index = (
        index_file.read_text(encoding="utf-8") if index_file.exists() else None
    )
    original_asset = (
        asset_file.read_text(encoding="utf-8") if asset_file.exists() else None
    )

    try:
        index_file.write_text("<html><body>frontend</body></html>", encoding="utf-8")
        asset_file.write_text("console.log('ok')", encoding="utf-8")

        monkeypatch.setattr(web_module, "FRONTEND_DIST_DIR", dist_dir)
        monkeypatch.setattr(web_module, "FRONTEND_INDEX_FILE", index_file)

        root_response = api_harness["client"].get("/")
        route_response = api_harness["client"].get("/tools/portfolio-balance")
        asset_response = api_harness["client"].get("/assets/app.js")

        assert root_response.status_code == 200
        assert "frontend" in root_response.text
        assert route_response.status_code == 200
        assert "frontend" in route_response.text
        assert asset_response.status_code == 200
        assert "console.log" in asset_response.text
    finally:
        if original_index is None:
            index_file.unlink(missing_ok=True)
        else:
            index_file.write_text(original_index, encoding="utf-8")
        if original_asset is None:
            asset_file.unlink(missing_ok=True)
        else:
            asset_file.write_text(original_asset, encoding="utf-8")


@pytest.mark.asyncio
async def test_global_exception_handler_returns_internal_server_error():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/boom",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
            "query_string": b"",
            "root_path": "",
        }
    )

    response = await unhandled_exception_handler(request, RuntimeError("boom"))

    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal server error"}'


def test_frontend_fallback_rejects_unknown_reserved_paths(api_harness):
    response = api_harness["client"].get("/api/private")

    assert response.status_code == 404


def test_development_frontend_redirects_root_and_preserves_route_query(api_harness, monkeypatch):
    monkeypatch.setenv("OPENTRADING_FRONTEND_DEV_URL", "http://127.0.0.1:4173/")
    client = api_harness["client"]
    for path in ("/", "/indicators/equities?platform=okx"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "http://127.0.0.1:4173" + path
        assert response.headers["cache-control"] == "no-store"


def test_development_frontend_keeps_api_health_and_docs_on_backend(api_harness, monkeypatch):
    monkeypatch.setenv("OPENTRADING_FRONTEND_DEV_URL", "http://127.0.0.1:4173")
    client = api_harness["client"]
    assert client.get("/health/live", follow_redirects=False).status_code == 200
    assert client.get("/docs", follow_redirects=False).status_code == 200
    assert client.get("/api/private", follow_redirects=False).status_code == 404


def test_dollar_liquidity_dashboard_api_is_retired():
    registered_paths = {getattr(route, "path", None) for route in main_module.app.routes}

    assert "/indicators/dli" not in registered_paths
