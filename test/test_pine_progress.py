import asyncio
import json
from threading import Event
from types import SimpleNamespace

import pytest

from app.contracts.chart_workspace import ChartBar, ChartBars, ChartSymbol, PineRunRequest, WorkspaceWrite
from app.infra.persistence.chart_workspace_repository import ChartWorkspaceStore
from app.infra.persistence.pine_record_repository import PineRecordStore
from app.main import app
from app.routers.chart_workspace import services
from app.services.chart_workspace_runs import ChartPineRuns
from test.test_chart_workspace import worker_input
from test.test_repair_contracts import export_fixture


@pytest.mark.asyncio
async def test_real_node_progress_and_results_reach_the_pine_api(tmp_path, api_harness, monkeypatch):
    payload = worker_input()
    entered, allow_market = asyncio.Event(), asyncio.Event()

    class Market:
        async def resolve(self, _):
            entered.set()
            await allow_market.wait()
            return ChartSymbol.model_validate(payload["symbol"])

        async def bars(self, *_args, **kwargs):
            return ChartBars(symbol=await self.resolve(""), timeframe="1m", source="controlled-exchange", bars=[
                ChartBar.model_validate(row) for row in payload["bars"] if row["time"] >= kwargs.get("start", 0)])

    store = ChartWorkspaceStore(tmp_path / "workspace")
    store.put("scripts", "test", WorkspaceWrite(name="Progress", data={"source": payload["source"]}))
    runs = ChartPineRuns(store, Market())
    app.dependency_overrides[services] = lambda: SimpleNamespace(runs=runs, store=store)
    client = api_harness["client"]
    request = PineRunRequest.model_validate(payload["request"])
    consumed, allow_commit = Event(), Event()
    original = PineRecordStore.consume_report

    def consume(self, stream):
        result = original(self, stream)
        consumed.set()
        if not allow_commit.wait(10):
            raise TimeoutError("Test did not release the result commit barrier")
        return result

    try:
        first = await runs.create(request, "http://127.0.0.1:1", recording="report")
        await asyncio.wait_for(entered.wait(), 5)
        loading = client.get(f"/api/v1/chart-workspace/pine-runs/{first.id}").json()
        assert loading["status"] == "loading"
        assert loading["progress"]["mode"] == "indeterminate"
        export_fixture("pine-loading.json", loading)
        await runs.cancel(first.id)
        cancelled = client.get(f"/api/v1/chart-workspace/pine-runs/{first.id}").json()
        assert cancelled["status"] == "cancelled"
        export_fixture("pine-cancelled.json", cancelled)

        monkeypatch.setattr(PineRecordStore, "consume_report", consume)
        allow_market.set()
        second = await runs.create(request, "http://127.0.0.1:1", recording="report")
        task = runs.tasks[second.id]
        assert await asyncio.to_thread(consumed.wait, 5), "The actual Node report producer was not consumed"
        saving = client.get(f"/api/v1/chart-workspace/pine-runs/{second.id}").json()
        assert saving["status"] == "running"
        assert saving["progress"]["phase"] == "saving"
        assert saving["progress"]["mode"] == "indeterminate"
        frame = json.loads((runs.folder(second.id) / "progress.json").read_text())
        assert frame["runId"] == second.id
        export_fixture("pine-saving.json", saving)
        progress_file = runs.folder(second.id) / "progress.json"
        original_frame = progress_file.read_bytes()
        progress_file.write_text('{"broken":', encoding="utf-8")
        unavailable = client.get(f"/api/v1/chart-workspace/pine-runs/{second.id}").json()
        assert unavailable["status"] == "running"
        assert unavailable["progress"]["mode"] == "indeterminate"
        progress_file.write_bytes(original_frame)
        allow_commit.set()
        await asyncio.wait_for(task, 5)
        completed = client.get(f"/api/v1/chart-workspace/pine-runs/{second.id}").json()
        assert completed["status"] == "completed", completed.get("error")
        assert completed["progress"] is None
        page = client.get(f"/api/v1/chart-workspace/pine-runs/{second.id}/records", params={"kind": "equity"}).json()
        assert page["total"] == len(payload["bars"])
        export_fixture("pine-completed.json", completed)
        export_fixture("pine-equity.json", page)
    finally:
        allow_commit.set()
        await runs.close()
