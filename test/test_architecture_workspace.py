import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from threading import Event
import time

import pytest
from fastapi import HTTPException

from app.contracts.chart_workspace import WorkspaceWrite
from app.infra.executor import run_workspace
from app.routers.chart_workspace import services, chart_save_document
from app.services.chart_workspace_runtime import ChartWorkspaceRuntime
from app.services.chart_workspace_seed import seed_workspace
from app.infra.persistence.chart_workspace_repository import ChartWorkspaceStore
from httpx import AsyncClient, ASGITransport
from contextlib import asynccontextmanager
from app.main import create_app


def test_seed_is_idempotent_under_concurrent_startup(tmp_path):
    store = ChartWorkspaceStore(tmp_path)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: seed_workspace(store), range(4)))
    assert len(store.list("scripts")) == 2
    assert len(store.list("watchlists")) == 1
    assert store.get("scripts", "opentrading-v7-2").version == 1


@pytest.mark.asyncio
async def test_requests_only_obtain_startup_owned_service_and_it_releases_ownership(tmp_path):
    first = await run_workspace(lambda: ChartWorkspaceRuntime(None, None, root=tmp_path))
    connection = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime_services=SimpleNamespace(require_api=lambda: SimpleNamespace(chart_workspace=first)))))
    assert all(item is first for item in await asyncio.gather(*(services(connection) for _ in range(8))))
    with pytest.raises(RuntimeError, match="已有 API"):
        await run_workspace(lambda: ChartWorkspaceRuntime(None, None, root=tmp_path))
    await first.close()
    with pytest.raises(HTTPException):
        await services(connection)
    second = await run_workspace(lambda: ChartWorkspaceRuntime(None, None, root=tmp_path))
    await second.close()


@pytest.mark.asyncio
async def test_locked_workspace_write_does_not_block_other_async_requests(tmp_path):
    store = ChartWorkspaceStore(tmp_path)
    locked = Event()
    def hold():
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            locked.set()
            time.sleep(.3)
    with ThreadPoolExecutor(1) as pool:
        holder = pool.submit(hold)
        await asyncio.to_thread(locked.wait)
        write = asyncio.create_task(chart_save_document("layouts", "x", WorkspaceWrite(name="x", data={}), service=SimpleNamespace(store=store)))
        start = time.monotonic()
        await asyncio.sleep(.03)
        assert time.monotonic() - start < .15
        assert not write.done()
        assert (await write).version == 1
        holder.result()


@pytest.mark.asyncio
async def test_first_parallel_http_requests_share_workspace_and_version_conflicts(tmp_path):
    app = create_app("api")
    @asynccontextmanager
    async def lifespan(_):
        workspace = await run_workspace(lambda: ChartWorkspaceRuntime(None, None, root=tmp_path))
        app.state.runtime_services = SimpleNamespace(require_api=lambda: SimpleNamespace(chart_workspace=workspace))
        try:
            yield
        finally:
            await workspace.close()
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        results = await asyncio.gather(*(client.get("/api/v1/chart-workspace/scripts") for _ in range(8)))
        assert all(response.status_code == 200 for response in results)
        assert all(response.json()[0]["version"] == 1 for response in results)
        writes = await asyncio.gather(*(client.put("/api/v1/chart-workspace/layouts/one", json={"name":"One","data":{},"expected_version":0}) for _ in range(2)))
        assert sorted(response.status_code for response in writes) == [200, 409]
