import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from app.domain.local_backtest import Bar, Intent, ProfitProtection, simulate
from app.infra.research_files import atomic_json, file_hash
from app.services.backtest_record_store import BacktestRecordStore, PAGE_SIZE, TAIL_SIZE
from scripts.local_backtest_worker import execute
from test.test_local_backtest_service import setup_service, complete


def test_paged_simulation_matches_in_memory_across_flush_boundaries(tmp_path):
    store = BacktestRecordStore(tmp_path/'records')
    bars = [Bar(i*60000, 100+(i%40), 102+(i%40), 99+(i%40), 101+(i%40), 1) for i in range(5200)]
    class Strategy:
        def on_bar(self, ctx):
            if len(ctx.history) % 7 == 0:
                return Intent('long' if len(ctx.history)%14 else 'short', stop_loss_pct=1,
                              profit_protection=ProfitProtection(2, 50))
    plain = simulate(bars, Strategy(), {}, warmup=10, step_ms=60000)
    paged = simulate(bars, Strategy(), {}, warmup=10, step_ms=60000, record_factory=store.collection)
    for kind in ('trades', 'signals', 'fills', 'events', 'equity', 'levels'):
        assert list(paged[kind]) == plain[kind]
        assert len(paged[kind].tail) < PAGE_SIZE+TAIL_SIZE
    assert plain['report'] == paged['report']
    candles = store.candle_index('a'*64, bars)
    manifest = store.seal(tmp_path/'run', paged, candles, 'fingerprint')
    restored = store.result(manifest)
    assert restored == plain
    assert store.records(manifest, 'equity', 10, 19)['items'] == plain['equity'][10:29]
    filtered = [p for p in plain['equity'] if 2000*60000 <= p['timestamp'] <= 4300*60000]
    page = store.records(manifest, 'equity', 1000, 100, 2000*60000, 4300*60000)
    assert page['total'] == len(filtered) and page['items'] == filtered[1000:1100]
    assert store.records(manifest, 'equity', 100000, 10)['items'] == []


def test_shared_datasets_and_records_do_not_duplicate_full_arrays_in_db(setup_service):
    service, first = complete(setup_service)
    second = service.rerun(first['id'])
    service.repository.claim()
    execute(service, second['id'], SimpleNamespace(load_ohlcv_range=lambda *a: pytest.fail('no fetch')))
    assert service.data_path(first['id']) == service.data_path(second['id'])
    first_manifest = service.record_store.manifest(service.directory(first['id']))
    second_manifest = service.record_store.manifest(service.directory(second['id']))
    assert first_manifest == second_manifest
    assert not (service.directory(second['id'])/'result.json').exists()
    assert not (service.directory(second['id'])/'data.json').exists()
    assert service.repository.records(second['id'], 'trades')['total'] == 0
    assert service.records(second['id'], 'trades')['total'] == first['report']['total_trades']
    assert service.artifacts(second['id'])['result_format'] == 'record-pages-v1'


def test_cancel_during_saving_preserves_computation_and_resumes(setup_service, monkeypatch):
    service, command, market = setup_service
    run = service.create(command)
    service.repository.claim()
    original = service.record_store.verify
    def cancel(manifest, progress=None):
        assert service.repository.get(run['id'])['status'] == 'saving'
        service.cancel(run['id'])
        progress(.5)
    monkeypatch.setattr(service.record_store, 'verify', cancel)
    with pytest.raises(InterruptedError, match='可恢复'):
        execute(service, run['id'], market)
    assert service.get(run['id'])['resume_available']
    monkeypatch.setattr(service.record_store, 'verify', original)
    resumed = service.resume(run['id'])
    service.repository.claim()
    monkeypatch.setattr('scripts.local_backtest_worker._execute', lambda *a: pytest.fail('completed calculation must not execute again'))
    execute(service, resumed['id'])
    assert service.get(resumed['id'])['status'] == 'completed'
    assert service.get(run['id'])['status'] == 'cancelled'
    assert service.get(resumed['id'])['parent_id'] == run['id']
    assert service.records(resumed['id'], 'trades')['total'] == 1


def test_published_result_corruption_is_detected(setup_service):
    service, run = complete(setup_service)
    manifest = service.record_store.manifest(service.directory(run['id']))
    part = manifest['arrays']['trades']['parts'][0]
    service.record_store.object_path(part['hash']).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='记录块校验失败'):
        service.records(run['id'], 'trades')
    with pytest.raises(ValueError, match='记录块校验失败'):
        service.verify_result(run)


def test_legacy_json_and_database_records_remain_readable(setup_service):
    service, first = complete(setup_service)
    result = service.result(first['id'])
    command = setup_service[1]
    legacy = service.create(command)
    service.repository.claim()
    folder = service.directory(legacy['id'])
    atomic_json(folder/'result.json', result)
    meta = {**legacy['metadata'], 'result_hash': file_hash(folder/'result.json')}
    candles = service.records(first['id'], 'candles')['items']
    assert service.repository.finish(legacy['id'], result, candles, meta)
    assert service.result(legacy['id']) == result
    assert service.records(legacy['id'], 'trades')['items'] == result['trades']
    assert json.loads(service.export(legacy['id'], 'json')['content'])['report'] == first['report']


@pytest.mark.skipif(os.name != 'nt', reason='Windows process interruption')
def test_windows_kill_during_publish_can_resume_in_new_process(setup_service, tmp_path):
    service, first = complete(setup_service)
    service.repository.patch(first['id'], status='interrupted')
    waiting = service.resume(first['id'])
    service.repository.claim()
    marker = tmp_path/'saving-entered.txt'
    code = '''import sys,time
from pathlib import Path
from app.infra.db import build_database_runtime
from config.settings import AppSettings
from app.services.local_backtest_service import LocalBacktestService
from app.services.backtest_record_store import BacktestRecordStore
from scripts.local_backtest_worker import execute
db=build_database_runtime(AppSettings(DATABASE_URL=sys.argv[1]))
s=LocalBacktestService(db,Path(sys.argv[2]))
def pause(self,manifest,progress=None):
    Path(sys.argv[4]).write_text('saving',encoding='utf8')
    time.sleep(30)
BacktestRecordStore.verify=pause
execute(s,sys.argv[3])
'''
    process = subprocess.Popen([sys.executable, '-c', code, service.repository.database.database_url,
        str(service.root), waiting['id'], str(marker)], cwd=Path(__file__).parents[1],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic()+15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert marker.exists(), process.stderr.read().decode() if process.poll() is not None else 'saving stage not reached'
        assert service.repository.get(waiting['id'])['status'] == 'saving'
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()
    service.repository.interrupt_active()
    resumed = service.resume(waiting['id'])
    service.repository.claim()
    execute(service, resumed['id'], SimpleNamespace(load_ohlcv_range=lambda *a: pytest.fail('must not fetch or compute')))
    assert service.repository.get(resumed['id'])['status'] == 'completed'
    assert service.result(resumed['id']) == service.result(first['id'])
