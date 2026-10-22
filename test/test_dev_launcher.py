from __future__ import annotations

import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import Mock

import pytest

from scripts.dev_launcher import Child, Launcher, read_endpoint
from scripts.launcher_windows import LauncherLock, ProcessJob, StopEvent, request_stop


def test_health_check_explains_startup_503_and_rejects_failed_worker(monkeypatch):
    opener = Mock()
    monkeypatch.setattr('scripts.dev_launcher.build_opener', lambda *_: opener)
    def response(payload):
        return HTTPError('http://127.0.0.1/health',503,'not ready',{},io.BytesIO(json.dumps(payload).encode()))
    opener.open.side_effect = response({'detail':'Initial market indicator collection has not succeeded'})
    assert read_endpoint('http://127.0.0.1/health') == (False,'等待首次市场数据采集完成')
    opener.open.side_effect = response({'detail':'worker failed','components':{'background_runtime':{'status':'failed'}}})
    with pytest.raises(RuntimeError,match='后台启动失败'):
        read_endpoint('http://127.0.0.1/health')


def test_child_exit_fails_startup_without_waiting_for_timeout():
    launcher = Launcher(root=Path('.'), settings=SimpleNamespace(API_PORT=8000,FRONTEND_DEV_PORT=4173),
        log=Mock(),job=Mock(),stop_event=Mock(),timeout=120)
    child = Mock();child.poll.return_value = 7
    launcher.children = [Child('后台',child,Mock(),True)]
    with pytest.raises(RuntimeError,match='退出码 7'):
        launcher.check_children()


def test_unready_endpoint_is_never_reported_as_success(monkeypatch):
    stop = Mock();stop.is_set.return_value = False
    log = Mock()
    launcher = Launcher(root=Path('.'),settings=SimpleNamespace(API_PORT=8000,FRONTEND_DEV_PORT=4173),
        log=log,job=Mock(),stop_event=stop,timeout=1)
    ticks = iter([0,0,0,0,2])
    monkeypatch.setattr('scripts.dev_launcher.time.monotonic',lambda:next(ticks,2))
    monkeypatch.setattr('scripts.dev_launcher.read_endpoint',lambda _: (False,'等待首次采集'))
    launcher.stop_requested = Mock();launcher.stop_requested.is_set.return_value = False
    with pytest.raises(RuntimeError,match='等待首次采集'):
        launcher.wait_ready('完整服务','http://127.0.0.1/health')
    assert all('已就绪' not in str(call) for call in log.write.call_args_list)


def test_old_ready_heartbeat_does_not_skip_new_worker_startup(monkeypatch):
    stop = Mock();stop.is_set.return_value = False
    launcher = Launcher(root=Path('.'),settings=SimpleNamespace(API_PORT=8000,FRONTEND_DEV_PORT=4173),
        log=Mock(),job=Mock(),stop_event=stop,timeout=1)
    ticks = iter([0,0,0,0,2])
    monkeypatch.setattr('scripts.dev_launcher.time.monotonic',lambda:next(ticks,2))
    monkeypatch.setattr('scripts.dev_launcher.read_endpoint',lambda _: (True,'就绪'))
    launcher.stop_requested = Mock();launcher.stop_requested.is_set.return_value = False
    with pytest.raises(RuntimeError,match='本次后台进程'):
        launcher.wait_ready('完整服务','http://127.0.0.1/health',needs_background=True)


@pytest.mark.asyncio
async def test_cache_connects_before_starting_concurrent_market_tasks():
    from app.runtime import AppRuntimeServices, InfraRuntimeServices, IndicatorRuntimeServices
    events = []
    async def cache_start(): events.append('cache')
    async def market_start(): events.append('market')
    services = AppRuntimeServices(infra=InfraRuntimeServices(object(),SimpleNamespace(connect_async=cache_start)),
                                  indicators=IndicatorRuntimeServices(object(),object()))
    services.api = SimpleNamespace(market=SimpleNamespace(binance_intel=SimpleNamespace(start=market_start)),
                                   research_alerts=None,trade_signal_evaluations=None)
    await services.start()
    assert events == ['cache','market']


@pytest.mark.skipif(os.name != 'nt',reason='Windows process lifetime')
def test_launcher_lock_prevents_duplicate_and_can_restart(tmp_path):
    first, second = LauncherLock(tmp_path/'launcher.lock'), LauncherLock(tmp_path/'launcher.lock')
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.close()
    assert second.acquire()
    second.close()


@pytest.mark.skipif(os.name != 'nt',reason='Windows stop event')
def test_stop_request_only_targets_same_project(tmp_path):
    event = StopEvent(tmp_path/'project-a')
    try:
        assert not request_stop(tmp_path/'project-b')
        assert not event.is_set()
        assert request_stop(tmp_path/'project-a')
        assert event.is_set()
    finally:
        event.close()


@pytest.mark.skipif(os.name != 'nt',reason='Windows job object')
def test_closing_job_stops_child_and_grandchild():
    job = ProcessJob()
    code = "import subprocess,sys,time;sys.stdin.readline();p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);print(p.pid,flush=True);time.sleep(120)"
    parent = subprocess.Popen([sys.executable,'-u','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    child_handle = None
    try:
        job.add(parent)
        parent.stdin.write('start\n');parent.stdin.flush()
        child_pid = int(parent.stdout.readline())
        api = ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        child_handle = api.OpenProcess(0x00100000,False,child_pid)
        assert child_handle
        job.close()
        assert parent.wait(timeout=5) is not None
        assert api.WaitForSingleObject(child_handle,5000) == 0
    finally:
        job.close()
        if child_handle:
            api.CloseHandle(child_handle)
        if parent.poll() is None:
            parent.kill();parent.wait()
        parent.stdin.close();parent.stdout.close()


def test_shutdown_cleans_up_partial_startup():
    log, job, stop = Mock(), Mock(), Mock()
    launcher = Launcher(root=Path('.'),settings=SimpleNamespace(API_PORT=8000,FRONTEND_DEV_PORT=4173),
        log=log,job=job,stop_event=stop)
    process = Mock();process.poll.return_value = 0
    reader = Mock()
    launcher.children = [Child('API',process,reader,True)]
    launcher.shutdown()
    job.close.assert_called_once()
    process.wait.assert_called_once()
    reader.join.assert_called_once()


@pytest.mark.asyncio
async def test_google_trends_handles_future_pandas_fillna_without_warning(monkeypatch):
    import warnings
    import pandas as pd
    from pytrends.request import TrendReq
    from app.services.indicators.sentiment_provider import SentimentProvider
    index = pd.DatetimeIndex(['2026-10-18'])
    def interest(_self):
        return pd.DataFrame({'buy bitcoin':[42.0], 'isPartial':pd.Series([None],index=index,dtype=object)},index=index).fillna(False)
    monkeypatch.setattr(TrendReq,'__init__',lambda self,**kwargs:None)
    monkeypatch.setattr(TrendReq,'build_payload',lambda *args,**kwargs:None)
    monkeypatch.setattr(TrendReq,'interest_over_time',interest)
    original = pd.get_option('future.no_silent_downcasting')
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always',FutureWarning)
        points = await SentimentProvider()._fetch_google_trends()
    assert points[0]['value'] == 42.0
    assert not [w for w in captured if issubclass(w.category,FutureWarning)]
    assert pd.get_option('future.no_silent_downcasting') == original
