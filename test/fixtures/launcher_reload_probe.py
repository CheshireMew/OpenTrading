"""Exercise real Windows console signals without sharing the user's console."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
from types import SimpleNamespace
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev_launcher import Launcher, SessionLog  # noqa: E402
from scripts.launcher_windows import ProcessJob, StopEvent, request_stop  # noqa: E402


APP = '''import json, os
VERSION = {version!r}

async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            event = await receive()
            if event['type'] == 'lifespan.startup':
                await send({{'type': 'lifespan.startup.complete'}})
            elif event['type'] == 'lifespan.shutdown':
                await send({{'type': 'lifespan.shutdown.complete'}})
                return
    else:
        body = json.dumps({{'pid': os.getpid(), 'version': VERSION}}).encode()
        await send({{'type': 'http.response.start', 'status': 200, 'headers': []}})
        await send({{'type': 'http.response.body', 'body': body}})
'''

WORKER = '''import signal, sys, time
def stop(*_):
    print('WORKER_STOPPED', flush=True)
    sys.exit(0)
signal.signal(signal.SIGBREAK, stop)
print('WORKER_READY', flush=True)
while True:
    time.sleep(.05)
'''


def probe(folder, stop_mode):
    folder.mkdir(parents=True, exist_ok=True)
    for name in ('app', 'config', 'utils'):
        (folder / name).mkdir()
    (folder / 'app/__init__.py').touch()
    source = folder / 'app/main.py'
    source.write_text(APP.format(version='original'), encoding='utf8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    os.environ['OPENTRADING_API_PORT'] = str(port)
    log, job, stop_event = SessionLog(folder / 'logs'), ProcessJob(), StopEvent(folder)
    launcher = Launcher(root=folder, settings=SimpleNamespace(API_PORT=port, FRONTEND_DEV_PORT=4173),
                        log=log, job=job, stop_event=stop_event)
    for name in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
        signal.signal(getattr(signal, name), launcher.handle_signal)
    opener = build_opener(ProxyHandler({}))

    def wait_version(version):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert not launcher.stopped(), 'API reload stopped the launcher'
            launcher.check_children()
            try:
                with opener.open(f'http://127.0.0.1:{port}/', timeout=.5) as response:
                    data = json.load(response)
                if data['version'] == version:
                    return data['pid']
            except OSError:
                pass
            time.sleep(.1)
        raise AssertionError(f'API did not serve {version}')

    try:
        api = launcher.start_api()
        siblings = [launcher.start_child(label, [sys.executable, '-u', '-c', WORKER])
                    for label in ('后台', '前端')]
        api_pids = [wait_version('original')]
        for version in ('after_first_reload', 'after_second_reload'):
            time.sleep(.6)  # Allow StatReload to record the initial mtime.
            source.write_text(APP.format(version=version), encoding='utf8')
            api_pids.append(wait_version(version))
            assert api.poll() is None
            assert all(child.poll() is None for child in siblings)
        assert len(set(api_pids)) == 3, 'Reload must replace only the API worker'
        assert not launcher.stopped()
        if stop_mode == 'close':
            api_windows = ctypes.WinDLL('kernel32', use_last_error=True)
            api_windows.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            api_windows.OpenProcess.restype = wintypes.HANDLE
            api_windows.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            api_windows.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = api_windows.OpenProcess(0x00100000, False, api_pids[-1])
            assert handle
            try:
                job.close()  # The same OS cleanup used when the launcher window closes.
                launcher.shutdown()
                assert api.poll() is not None
                assert all(child.poll() is not None for child in siblings)
                assert api_windows.WaitForSingleObject(handle, 5000) == 0, 'API worker survived its launcher'
            finally:
                api_windows.CloseHandle(handle)
            print('PROBE_PASSED', flush=True)
            return
        if stop_mode == 'signal':
            api_windows = ctypes.WinDLL('kernel32', use_last_error=True)
            assert api_windows.GenerateConsoleCtrlEvent(signal.CTRL_C_EVENT, 0)
            deadline = time.monotonic() + 3
            while not launcher.stop_requested.is_set() and time.monotonic() < deadline:
                time.sleep(.05)
            assert launcher.stop_requested.is_set(), 'User Ctrl+C must still stop the launcher'
        elif stop_mode == 'external':
            assert request_stop(folder)
        elif stop_mode == 'q':
            import msvcrt

            sys.stdin = SimpleNamespace(isatty=lambda: True)
            msvcrt.kbhit = lambda: True
            msvcrt.getwch = lambda: 'Q'
        launcher.monitor()
        launcher.shutdown()
        assert api.returncode == 0, f'API did not stop gracefully: {api.returncode}'
        assert all(child.returncode == 0 for child in siblings), 'Sibling services were forcibly killed'
        output = log.path.read_text(encoding='utf8')
        assert output.count('Application shutdown complete.') == 3
        assert 'Stopping reloader process' in output
        assert output.count('WORKER_STOPPED') == 2
        print('PROBE_PASSED', flush=True)
    finally:
        if any(child.process.poll() is None for child in launcher.children):
            launcher.shutdown()
        stop_event.close()
        job.close()
        log.close()


if __name__ == '__main__':
    probe(Path(sys.argv[1]), sys.argv[2])
