import asyncio

import pytest

from app.contracts.chart_workspace import ChartBars, ChartBar, ChartSymbol, PineRunRequest, WorkspaceWrite
from app.services.chart_workspace_runs import ChartPineRuns, PineCapacityError
from app.services.chart_workspace_store import ChartWorkspaceStore
from test.test_chart_workspace import worker_input


def setup_runs(tmp_path, market, **limits):
    payload = worker_input()
    store = ChartWorkspaceStore(tmp_path)
    store.put("scripts", "test", WorkspaceWrite(name="Test", data={"source": payload["source"]}))
    return ChartPineRuns(store, market, **limits), PineRunRequest.model_validate(payload["request"])


@pytest.mark.asyncio
async def test_bounded_queue_releases_slots_and_rejects_after_shutdown(tmp_path):
    class BlockedMarket:
        async def resolve(self, _):
            await asyncio.Event().wait()

    runs, request = setup_runs(tmp_path, BlockedMarket(), concurrency=1, queue_limit=1)
    first = await runs.create(request, "http://127.0.0.1:1")
    await asyncio.sleep(0)
    second = await runs.create(request, "http://127.0.0.1:1")
    with pytest.raises(PineCapacityError, match="队列已满"):
        await runs.create(request, "http://127.0.0.1:1")
    async with asyncio.timeout(3):
        while runs.get(first.id).status == "queued":
            await asyncio.sleep(.01)
    assert runs.get(first.id).status == "loading"
    assert runs.get(second.id).status == "queued"
    await runs.cancel(first.id)
    async with asyncio.timeout(3):
        while runs.get(second.id).status == "queued":
            await asyncio.sleep(.01)
    assert runs.get(first.id).status == "cancelled"
    assert runs.get(second.id).status == "loading"
    await runs.close()
    assert runs.get(second.id).status == "interrupted"
    assert not runs.tasks and not runs.processes
    with pytest.raises(PineCapacityError, match="已关闭"):
        await runs.create(request, "http://127.0.0.1:1")


@pytest.mark.asyncio
async def test_queue_deadline_is_a_persisted_terminal_state(tmp_path):
    class BlockedMarket:
        async def resolve(self, _):
            await asyncio.Event().wait()

    runs, request = setup_runs(tmp_path, BlockedMarket(), concurrency=1, queue_limit=1, queue_timeout=.03)
    await runs.create(request, "http://127.0.0.1:1")
    await asyncio.sleep(0)
    queued = await runs.create(request, "http://127.0.0.1:1")
    await runs.tasks[queued.id]
    assert runs.get(queued.id).status == "failed"
    assert "等待" in runs.get(queued.id).error
    await runs.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("termination", ["timeout", "cancel", "close", "spawn_cancel"])
@pytest.mark.parametrize("recording", ["research", "report"])
async def test_real_hung_node_process_exits_on_every_termination(tmp_path, monkeypatch, termination, recording):
    import app.services.chart_workspace_runs as module
    from app.infra.worker_process import start_worker
    payload = worker_input()

    class Market:
        async def resolve(self, _):
            return ChartSymbol.model_validate(payload["symbol"])

        async def bars(self, *args, **kwargs):
            return ChartBars(symbol=await self.resolve(""), timeframe="1m", source="fixture",
                             bars=[ChartBar.model_validate(row) for row in payload["bars"] if row["time"] >= kwargs.get("start", 0)])

    worker = tmp_path / "hung.mjs"
    worker.write_text("process.stdin.once('data', () => { setInterval(() => {}, 1000) });", encoding="utf-8")
    monkeypatch.setattr(module, "freeze_engine", lambda _: "fixture-engine")
    monkeypatch.setattr(module, "engine_worker", lambda *_: worker)
    children = []
    from threading import Event
    import time
    spawning = Event()

    def start(command, **kwargs):
        spawning.set()
        if termination == "spawn_cancel":
            time.sleep(.15)
        process, job = start_worker([command[0], str(worker), *command[2:]], **kwargs)
        children.append(process)
        return process, job

    monkeypatch.setattr(module, "start_worker", start)
    runs, request = setup_runs(tmp_path, Market(), timeout=.5)
    run = await runs.create(request, "http://127.0.0.1:1", recording=recording)
    task = runs.tasks[run.id]
    for _ in range(100):
        if children or termination == "spawn_cancel" and spawning.is_set():
            break
        await asyncio.sleep(.01)
    assert children or spawning.is_set(), "test never reached the real process boundary"
    if termination in {"cancel", "spawn_cancel"}:
        await runs.cancel(run.id)
    elif termination == "close":
        await runs.close()
    else:
        await task
    assert runs.get(run.id).status == {"timeout": "failed", "cancel": "cancelled", "close": "interrupted", "spawn_cancel": "cancelled"}[termination]
    assert children
    assert all(child.poll() is not None for child in children)
    assert not runs.processes
    await runs.close()
