import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.contracts.local_backtest import LocalBacktestCommand
from app.services.local_backtest_service import LocalBacktestService
from app.services.market.history_range_coordinator import OhlcvRangeResult
from app.infra.db.schema_runtime import verify_database_schema
from scripts.local_backtest_worker import execute


@pytest.fixture
def setup_service(installed_database_runtime, tmp_path, monkeypatch):
    root = tmp_path / "runs"
    service = LocalBacktestService(installed_database_runtime, root)
    source = tmp_path / "test_strategy.py"
    source.write_text('''from app.domain.local_backtest import Intent
STRATEGY = dict(id="test_strategy", name="test", description="test", api_version="1", warmup_bars=1, parameters={})
def on_bar(c):
    return Intent("long", 10, 20) if len(c.history)==2 else None
''', encoding="utf-8")
    monkeypatch.setattr("app.services.local_backtest_service.strategy_path", lambda identifier: source)
    monkeypatch.setattr("app.services.local_backtest_service.ExchangeGateway", lambda *a: SimpleNamespace(exchange=SimpleNamespace(timeframes={"1h": "1h"})))
    start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [[start + i * 3600000, 100, 101, 99, 100, 1] for i in range(-1, 4)]
    market = SimpleNamespace(load_ohlcv_range=lambda *a: OhlcvRangeResult(rows, []))
    command = LocalBacktestCommand(strategy="test_strategy", start="2025-01-01T00:00:00Z", end="2025-01-01T04:00:00Z")
    return service, command, market


def complete(setup_service):
    service, command, market = setup_service
    run = service.create(command)
    assert service.repository.claim() == run["id"]
    execute(service, run["id"], market)
    return service, service.repository.get(run["id"])


def test_schema_and_reproducible_results(setup_service):
    service, run = complete(setup_service)
    verify_database_schema(service.repository.database)
    assert run["status"] == "completed"
    original = json.loads(service.export(run["id"], "json")["content"])
    second = service.rerun(run["id"])
    assert service.repository.claim() == second["id"]
    execute(service, second["id"], SimpleNamespace(load_ohlcv_range=lambda *a: pytest.fail("重跑不应下载")))
    replay = json.loads(service.export(second["id"], "json")["content"])
    for key in ("report", "trades", "signals", "equity", "fills", "levels"):
        assert original[key] == replay[key]
    assert replay["run"]["parent_id"] == run["id"]
    assert "entry_time" in service.export(run["id"], "trades")["content"]
    assert service.records(run["id"], "candles", 1, 2)["total"] == 5
    assert len(service.records(run["id"], "candles", 1, 2)["items"]) == 2


def test_fine_execution_snapshot_is_frozen_and_reused_without_download(setup_service):
    service,command,market=setup_service
    command=command.model_copy(update={'execution_timeframe':'5m','intrabar_profit_protection':True})
    start=int(command.start.timestamp()*1000)
    fine=[[start+i*300000,100,101,99,100,1] for i in range(48)]
    fetch=lambda symbol,tf,*args: OhlcvRangeResult(fine,[]) if tf=='5m' else market.load_ohlcv_range(symbol,tf,*args)
    run=service.create(command);assert service.repository.claim()==run['id']
    execute(service,run['id'],SimpleNamespace(load_ohlcv_range=fetch))
    done=service.repository.get(run['id'])
    assert done['metadata']['execution_matched_candles']==4 and done['metadata']['execution_fallback_candles']==0
    before=json.loads((service.directory(run['id'])/'result.json').read_text(encoding='utf8'))
    other=service.rerun(run['id']);assert service.repository.claim()==other['id']
    execute(service,other['id'],SimpleNamespace(load_ohlcv_range=lambda *a:pytest.fail('细行情重跑不能下载')))
    after=json.loads((service.directory(other['id'])/'result.json').read_text(encoding='utf8'))
    assert before==after
    assert (service.directory(other['id'])/'execution_data.json').read_bytes()==(service.directory(run['id'])/'execution_data.json').read_bytes()
    (service.directory(other['id'])/'execution_data.json').write_text('[]',encoding='utf8')
    with pytest.raises(ValueError,match='细周期行情快照校验失败'):service.rerun(other['id'])


def test_queue_cancel_and_restart(setup_service):
    service, command, market = setup_service
    run = service.create(command)
    service.cancel(run["id"])
    assert service.repository.claim() is None
    other = service.create(command)
    assert service.repository.claim() == other["id"]
    service.repository.interrupt_active()
    assert service.repository.get(other["id"])["status"] == "interrupted"
    service.archive(other["id"])
    assert service.repository.get(other["id"])["status"] == "interrupted"
    assert service.repository.list(archived=True)["total"] == 1


def test_cancel_during_computation_cannot_complete(setup_service):
    service, command, market = setup_service
    run = service.create(command)
    service.repository.claim()
    old = service.repository.patch
    def cancel_progress(identifier, **kwargs):
        if "progress" in kwargs:
            service.cancel(identifier)
        return old(identifier, **kwargs)
    service.repository.patch = cancel_progress
    with pytest.raises(InterruptedError):
        execute(service, run["id"], market)
    assert service.repository.get(run["id"])["status"] == "cancelled"
    assert service.records(run["id"], "trades")["total"] == 0


def test_missing_and_tampered_snapshot(setup_service):
    service, command, market = setup_service
    run = service.create(command)
    with pytest.raises(ValueError, match="快照"):
        service.rerun(run["id"])
    service.repository.claim()
    execute(service, run["id"], market)
    (service.directory(run["id"]) / "data.json").write_text("[]")
    with pytest.raises(ValueError, match="校验"):
        service.rerun(run["id"])


def test_invalid_history_cannot_create_results(setup_service):
    service, command, _ = setup_service
    run = service.create(command)
    service.repository.claim()
    with pytest.raises(RuntimeError, match="Incomplete"):
        execute(service, run["id"], SimpleNamespace(load_ohlcv_range=lambda *a: OhlcvRangeResult([], [(1, 2)])))
    assert service.records(run["id"], "equity")["total"] == 0


def test_http_and_cli_same_input(api_harness, setup_service, monkeypatch):
    from app.routers.local_backtests import service as dependency
    from scripts.local_backtest_cli import execute as cli_execute
    from scripts.research_cli import build_parser
    service, command, market = setup_service
    client = api_harness["client"]
    client.app.dependency_overrides[dependency] = lambda: service
    monkeypatch.setattr("scripts.local_backtest_cli.build_database_runtime", lambda settings: service.repository.database)
    monkeypatch.setattr("scripts.local_backtest_cli.LocalBacktestService", lambda database: service)
    monkeypatch.setattr(service.repository.database, "dispose", lambda: None)
    try:
        response = client.post("/api/v1/local-backtests", json=command.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        first = response.json()
        args = build_parser().parse_args(["backtest", "run", "--strategy", "test_strategy", "--start", "2025-01-01T00:00:00Z", "--end", "2025-01-01T04:00:00Z"])
        second = asyncio.run(cli_execute(args))
        assert first["config"] == second["config"]
        for identifier in (first["id"], second["id"]):
            assert service.repository.claim() == identifier
            execute(service, identifier, market)
        assert service.repository.get(first["id"])["report"] == service.repository.get(second["id"])["report"]
        response = client.get(f"/api/v1/local-backtests/{first['id']}/records/trades")
        assert response.status_code == 200
        assert response.json()["total"] == 1
    finally:
        client.app.dependency_overrides.pop(dependency, None)


def test_strategy_metadata_is_read_without_running_code():
    from app.services.local_backtest_strategies import inspect_strategy, validate_parameters
    source = b'''STRATEGY = dict(id="test", name="test", description="", api_version="1", warmup_bars=1, parameters={"n": {"type": "int", "default": 2, "min": 1, "max": 3}})
raise RuntimeError("must not execute in API")
def on_bar(context): return None
'''
    metadata = inspect_strategy(source, "test.py")
    assert validate_parameters(metadata, {}) == {"n": 2}
    for parameters in ({"n": True}, {"n": 0}, {"other": 1}):
        with pytest.raises(ValueError):
            validate_parameters(metadata, parameters)
    with pytest.raises(ValueError, match="辅助模块"):
        inspect_strategy(source + b"\nimport local_helper", "test.py")
    with pytest.raises(ValueError, match="无法解析"):
        inspect_strategy(b"def broken:", "broken.py")


def test_sampled_equity_keeps_extrema_and_exports_match_database(setup_service):
    service, run = complete(setup_service)
    full = service.records(run["id"], "equity")["items"]
    sampled = service.sampled_equity(run["id"], 6)["items"]
    assert sampled[0] == full[0] and sampled[-1] == full[-1]
    for key in ("equity", "drawdown_pct"):
        assert min(v[key] for v in sampled) == min(v[key] for v in full)
        assert max(v[key] for v in sampled) == max(v[key] for v in full)
    import csv
    import io
    exported = list(csv.DictReader(io.StringIO(service.export(run["id"], "equity")["content"])))
    assert [float(v["equity"]) for v in exported] == [v["equity"] for v in full]


def test_real_subprocess_cancel_and_runtime_shutdown(setup_service, tmp_path, api_harness):
    from app.services.local_backtest_runtime import LocalBacktestRuntime
    from app.services.local_backtest_service import write_json
    from app.services.local_backtest_strategies import digest
    from app.routers.local_backtests import service as dependency
    service, command, market = setup_service
    service.root = tmp_path / "local_backtests"
    runtime = LocalBacktestRuntime(service.repository.database)
    runtime.service = service

    def slow_run():
        run = service.create(command)
        folder = service.directory(run["id"])
        source = (folder / "strategy.py").read_bytes() + b'\nimport time\ndef on_bar(c):\n    time.sleep(10)\n    return None\n'
        (folder / "strategy.py").write_bytes(source)
        write_json(folder / "data.json", market.load_ohlcv_range().rows)
        metadata = {**run["metadata"], "strategy_hash": digest(source), "data_hash": digest((folder / "data.json").read_bytes())}
        write_json(folder / "metadata.json", metadata)
        service.repository.patch(run["id"], metadata=metadata)
        return run["id"]

    async def until(check):
        async with asyncio.timeout(20):
            while not check():
                await asyncio.sleep(.1)

    async def scenario():
        first, second = slow_run(), slow_run()
        await runtime.start()
        try:
            await until(lambda: service.repository.get(first)["status"] == "running")
            assert service.repository.get(second)["status"] == "queued"
            response = await asyncio.to_thread(api_harness["client"].get, f"/api/v1/local-backtests/{first}")
            assert response.status_code == 200 and response.json()["status"] == "running"
            process = runtime.process
            service.cancel(first)
            await until(lambda: process.poll() is not None)
            assert service.repository.get(first)["status"] == "cancelled"
            await until(lambda: service.repository.get(second)["status"] == "running")
            process = runtime.process
            await runtime.shutdown()
            assert process.poll() is not None
            assert service.repository.get(second)["status"] == "interrupted"
        finally:
            await runtime.shutdown()
    client = api_harness["client"]
    client.app.dependency_overrides[dependency] = lambda: service
    try:
        asyncio.run(scenario())
    finally:
        client.app.dependency_overrides.pop(dependency, None)


def test_rerun_rejects_previous_engine_rules(setup_service):
    from app.services.local_backtest_service import write_json
    service, run = complete(setup_service)
    folder = service.directory(run["id"])
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    metadata["environment"]["engine"] = "1"
    write_json(folder / "metadata.json", metadata)
    with pytest.raises(ValueError, match="版本"):
        service.rerun(run["id"])


@pytest.mark.skipif(os.name != "nt", reason="Windows process ownership")
def test_killed_background_reaps_worker_tree_and_restart_continues_queue(setup_service, tmp_path):
    import ctypes
    from ctypes import wintypes
    from app.services.local_backtest_service import write_json
    from app.services.local_backtest_strategies import digest
    from app.services.local_backtest_runtime import LocalBacktestRuntime
    service, command, market = setup_service
    service.root = tmp_path / "local_backtests"
    runs = [service.create(command), service.create(command)]
    for index, run in enumerate(runs):
        folder = service.directory(run["id"])
        source = (folder / "strategy.py").read_bytes()
        if index == 0:
            source += b'''
import subprocess, sys, time
from pathlib import Path
def on_bar(c):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], creationflags=subprocess.CREATE_NO_WINDOW)
    Path(__file__).with_name("descendant.pid").write_text(str(child.pid))
    time.sleep(120)
'''
        (folder / "strategy.py").write_bytes(source)
        write_json(folder / "data.json", market.load_ohlcv_range().rows)
        metadata = {**run["metadata"], "strategy_hash": digest(source),
                    "data_hash": digest((folder / "data.json").read_bytes())}
        write_json(folder / "metadata.json", metadata)
        service.repository.patch(run["id"], metadata=metadata)

    program = '''
import asyncio
from pathlib import Path
from app.infra.db import build_database_runtime
from app.services.local_backtest_runtime import LocalBacktestRuntime
from config import settings
async def main():
    runtime = LocalBacktestRuntime(build_database_runtime(settings))
    await runtime.start()
    while runtime.process is None:
        await asyncio.sleep(.05)
    (settings.RUNTIME_ROOT_DIR / "worker.pid").write_text(str(runtime.process.pid))
    await asyncio.sleep(120)
asyncio.run(main())
'''
    env = {**os.environ, "DATABASE_URL": service.repository.database.database_url,
           "RUNTIME_ROOT_DIR": str(tmp_path), "PYTHONUTF8": "1"}
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handles = []
    with (tmp_path / "owner.log").open("w", encoding="utf-8") as output:
        owner = subprocess.Popen([sys.executable, "-c", program], env=env, stdout=output,
                                 stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            worker_pid = tmp_path / "worker.pid"
            descendant_pid = service.directory(runs[0]["id"]) / "descendant.pid"
            deadline = time.monotonic() + 30
            while not (worker_pid.exists() and descendant_pid.exists()):
                assert owner.poll() is None, (tmp_path / "owner.log").read_text(encoding="utf-8")
                assert time.monotonic() < deadline, "Worker did not enter slow strategy"
                time.sleep(.1)
            for file in (worker_pid, descendant_pid):
                handle = api.OpenProcess(0x100000, False, int(file.read_text()))
                assert handle
                handles.append(handle)
            assert service.repository.get(runs[0]["id"])["status"] == "running"
            assert service.repository.get(runs[1]["id"])["status"] == "queued"
            owner.kill()  # No shutdown handler or finally block can run.
            owner.wait(timeout=10)
            for handle in handles:
                assert api.WaitForSingleObject(handle, 10000) == 0, "Orphan worker/descendant survived"

            async def restart():
                runtime = LocalBacktestRuntime(service.repository.database)
                runtime.service = service
                await runtime.start()
                try:
                    assert service.repository.get(runs[0]["id"])["status"] == "interrupted"
                    async with asyncio.timeout(30):
                        while service.repository.get(runs[1]["id"])["status"] not in {"completed", "failed"}:
                            await asyncio.sleep(.1)
                    assert service.repository.get(runs[1]["id"])["status"] == "completed"
                    assert service.records(runs[0]["id"], "trades")["total"] == 0
                finally:
                    await runtime.shutdown()
            asyncio.run(restart())
        finally:
            if owner.poll() is None:
                owner.kill()
            owner.wait(timeout=10)
            for handle in handles:
                api.CloseHandle(handle)
