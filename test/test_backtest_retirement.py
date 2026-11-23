"""Retired research entry points stay closed while Pine and investment tools remain usable."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.background_runtime import BackgroundRuntimeController, BackgroundRuntimeStatus
from app.main import create_app
from config import settings
from scripts.research_cli import build_parser


def test_only_pine_strategy_routes_remain_and_old_apis_return_not_found():
    app = create_app("api")
    paths = app.openapi()["paths"]
    retired = ("/api/v1/local-backtests", "/api/v1/parameter-sweeps", "/api/v1/research-results", "/api/v1/tools/portfolios", "/api/v1/research/reports")
    assert not any(path.startswith(retired) for path in paths)
    assert "/api/v1/chart-workspace/pine-runs" in paths
    assert any("/tools/" in path and "dca" in path for path in paths)
    client = TestClient(app)
    for prefix in retired:
        assert client.get(prefix).status_code == 404


@pytest.mark.parametrize("command", ["backtest", "sweep", "study", "catalog"])
def test_retired_cli_commands_cannot_submit_jobs(command):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args([command])
    assert error.value.code == 2
    assert build_parser().parse_args(["asset", "BTC/USDT"]).resource == "asset"


@pytest.mark.asyncio
async def test_background_starts_without_a_python_backtest_queue(tmp_path, monkeypatch):
    events = []

    class Scheduler:
        async def start(self, _owner):
            events.append("market-start")

        async def shutdown(self):
            events.append("market-stop")

    background = SimpleNamespace(market_scheduler=Scheduler())
    # No database/queue capability is provided; startup must not attempt a claim.
    runtime = SimpleNamespace(
        infra=SimpleNamespace(runtime_status=None, market_data=None),
        background=background, require_background=lambda: background,
    )
    monkeypatch.setattr(settings, "BACKGROUND_RUNTIME_LOCK_PATH", tmp_path / "background.lock")
    controller = BackgroundRuntimeController(runtime, role="background")
    try:
        await controller.start()
        await controller.wait_until_started()
        assert controller.state.status == BackgroundRuntimeStatus.READY
        assert events == ["market-start"]
    finally:
        await controller.shutdown()
    assert events == ["market-start", "market-stop"]
