"""One terminal owns the API, background worker, Vite and optional local Redis."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

from scripts.launcher_windows import LauncherLock, ProcessJob, StopEvent, request_stop

ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
HEALTH_ACCESS = re.compile(r'"(?:GET|HEAD) /health(?:/live)? HTTP/[^\"]+" (\d{3})')
HEALTH_DETAILS = {
    'Background worker has not reported readiness': '等待后台进程报告就绪',
    'Background worker is not ready or its heartbeat is stale': '后台任务正在启动或心跳尚未更新',
    'Initial market indicator collection has not succeeded': '等待首次市场数据采集完成',
    'Binance market snapshot is not ready': '等待币安行情快照与连接就绪',
    'Background services failed': '后台服务启动失败',
    'Background runtime failed': '后台任务启动失败',
}


class SessionLog:
    def __init__(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / (datetime.now().strftime('%Y%m%d-%H%M%S') + f'-{os.getpid()}.log')
        self.file = self.path.open('a', encoding='utf8', buffering=1)
        self.lock = threading.Lock()

    def write(self, label, message, *, console=True):
        line = ANSI.sub('', str(message)).rstrip()
        if not line:
            return
        rendered = f'{datetime.now():%H:%M:%S} [{label}] {line}'
        with self.lock:
            self.file.write(rendered + '\n')
            if console:
                print(rendered, flush=True)

    def close(self):
        self.file.close()


@dataclass
class Child:
    label: str
    process: subprocess.Popen
    reader: threading.Thread
    critical: bool


def read_endpoint(url):
    opener = build_opener(ProxyHandler({}))  # Local checks must not go through a system proxy.
    try:
        response = opener.open(Request(url, headers={'User-Agent':'OpenTrading-Launcher'}), timeout=2)
    except HTTPError as exc:
        response = exc
    except (URLError, OSError, TimeoutError):
        return False, '等待服务开始监听'
    with response:
        status = response.status
        body = response.read()
    if status == 200:
        return True, '就绪'
    try:
        payload = json.loads(body)
        detail = payload.get('detail', f'HTTP {status}')
        component = payload.get('components', {}).get('background_runtime')
        if isinstance(component, dict) and component.get('status') == 'failed':
            raise RuntimeError('后台启动失败，请查看上面的 [后台] 日志。')
    except (ValueError, AttributeError):
        detail = f'HTTP {status}'
    return False, HEALTH_DETAILS.get(detail, detail)


def port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=.5):
            return True
    except OSError:
        return False


class Launcher:
    def __init__(self, *, root, settings, log, job, stop_event, timeout=120):
        self.root, self.settings, self.log = root, settings, log
        self.job, self.external_stop = job, stop_event
        self.stop_requested = threading.Event()
        self.background_ready = threading.Event()
        self.startup_complete = threading.Event()
        self.children = []
        self.timeout = timeout
        self.api_port = int(os.getenv('OPENTRADING_API_PORT', settings.API_PORT))
        self.frontend_port = int(os.getenv('OPENTRADING_FRONTEND_PORT', settings.FRONTEND_DEV_PORT))
        self.api_url = f'http://127.0.0.1:{self.api_port}'
        self.frontend_url = f'http://127.0.0.1:{self.frontend_port}'
        self.environment = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
            OPENTRADING_API_HOST='127.0.0.1', OPENTRADING_API_PORT=str(self.api_port),
            OPENTRADING_FRONTEND_HOST='127.0.0.1', OPENTRADING_FRONTEND_PORT=str(self.frontend_port),
            OPENTRADING_FRONTEND_DEV_URL=self.frontend_url, NO_COLOR='1')

    def stopped(self):
        return self.stop_requested.is_set() or self.external_stop.is_set()

    def start_child(self, label, command, *, cwd=None, env=None, critical=True):
        process = subprocess.Popen(command, cwd=cwd or self.root, env={**self.environment, **(env or {})},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            text=True, encoding='utf8', errors='replace', bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        try:
            self.job.add(process)
        except BaseException:
            process.kill()
            process.wait()
            raise
        def stream():
            with process.stdout:
                for line in process.stdout:
                    if label == '后台' and line.strip() == 'OPENTRADING_BACKGROUND_READY':
                        self.background_ready.set()
                        self.log.write(label, '本次后台采集和任务调度已就绪。')
                        continue
                    health = HEALTH_ACCESS.search(line)
                    show = not health or (self.startup_complete.is_set() and health[1] != '200')
                    self.log.write(label, line, console=show)
        reader = threading.Thread(target=stream, name=f'launcher-{label}', daemon=True)
        reader.start()
        self.children.append(Child(label, process, reader, critical))
        return process

    def check_children(self):
        for child in self.children:
            code = child.process.poll()
            if child.critical and code is not None:
                raise RuntimeError(f'{child.label} 进程已退出（退出码 {code}），请查看上面的对应日志。')

    def run_step(self, label, command, timeout=120):
        process = self.start_child(label, command, critical=False)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if self.stopped():
                raise KeyboardInterrupt
            if time.monotonic() >= deadline:
                raise RuntimeError(f'{label} 未能在 {timeout} 秒内完成。')
            self.stop_requested.wait(.2)
        if process.returncode:
            raise RuntimeError(f'{label} 失败（退出码 {process.returncode}）。')

    def wait_ready(self, label, url, *, needs_background=False):
        deadline = time.monotonic() + self.timeout
        previous, last_report, detail = None, 0, '等待服务开始监听'
        while time.monotonic() < deadline:
            if self.stopped():
                raise KeyboardInterrupt
            self.check_children()
            ready, detail = read_endpoint(url)
            if ready and needs_background and not self.background_ready.is_set():
                ready, detail = False, '等待本次后台进程完成首次采集'
            if ready:
                self.log.write('启动', f'{label}已就绪。')
                return
            if detail != previous or time.monotonic() - last_report >= 10:
                self.log.write('等待', f'{label}：{detail}')
                previous, last_report = detail, time.monotonic()
            self.stop_requested.wait(1)
        raise RuntimeError(f'{label}在 {self.timeout} 秒内未就绪：{detail}。完整日志：{self.log.path}')

    def ensure_redis(self):
        from redis import Redis
        from redis.backoff import NoBackoff
        from redis.retry import Retry
        host = self.settings.REDIS_HOST
        host = '127.0.0.1' if host.lower() == 'localhost' else host
        def ping():
            client = Redis(host=host, port=self.settings.REDIS_PORT, password=self.settings.REDIS_PASSWORD or None,
                           socket_connect_timeout=.5, socket_timeout=1, retry=Retry(NoBackoff(), 0), retry_on_error=[])
            try:
                return bool(client.ping())
            except Exception:
                return False
            finally:
                client.close()
        if ping():
            self.log.write('缓存', 'Redis 已连接，使用现有实例。')
            return
        if host not in ('127.0.0.1', '::1'):
            self.log.write('缓存', '远程 Redis 暂不可用，将使用应用的内存缓存。')
            return
        executable = os.getenv('OPENTRADING_REDIS_EXE') or shutil.which('redis-server.exe')
        if not executable and Path('D:/Tools/Redis/redis-server.exe').is_file():
            executable = 'D:/Tools/Redis/redis-server.exe'
        if not executable:
            self.log.write('缓存', '未找到本地 Redis，使用应用的内存缓存。')
            return
        if port_open(host, self.settings.REDIS_PORT):
            raise RuntimeError('Redis 端口已有监听，但连接验证失败，请检查 REDIS_PASSWORD 与端口配置。')
        folder = self.settings.RUNTIME_ROOT_DIR / 'redis'
        folder.mkdir(parents=True, exist_ok=True)
        def quoted(value):
            return '"' + str(value).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r') + '"'
        config = '\n'.join([f'bind {host}', f'port {self.settings.REDIS_PORT}', f'dir {quoted(folder.as_posix())}',
            'save ""', 'appendonly no', 'logfile ""', 'loglevel warning', 'maxmemory 256mb', 'maxmemory-policy allkeys-lru',
            *([f'requirepass {quoted(self.settings.REDIS_PASSWORD)}'] if self.settings.REDIS_PASSWORD else [])])
        path = folder / 'launcher.conf'
        path.write_text(config + '\n', encoding='utf8')
        self.log.write('缓存', '以当前用户启动本地 Redis，退出启动器时一并停止。')
        process = self.start_child('Redis', [executable, str(path)], cwd=folder, critical=False)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and process.poll() is None:
            if ping():
                self.log.write('缓存', '本地 Redis 已就绪。')
                return
            if self.stopped():
                raise KeyboardInterrupt
            self.stop_requested.wait(.2)
        raise RuntimeError('本地 Redis 启动失败，请查看上面的 [Redis] 日志。')

    def start(self):
        node = shutil.which('node.exe') or shutil.which('node')
        vite = self.root / 'frontend/node_modules/vite/bin/vite.js'
        if not node or not vite.is_file():
            raise RuntimeError('未找到 Node.js 或前端依赖，请先按 README 安装前端环境。')
        for label, port in (('API', self.api_port), ('前端', self.frontend_port)):
            if port_open('127.0.0.1', port):
                raise RuntimeError(f'{label}端口 {port} 已被占用。请关闭旧的 OpenTrading 启动窗口后重试；不会终止其他程序。')
        self.run_step('依赖', ['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
                               '-File', str(self.root / 'scripts/start_local_dependencies.ps1')])
        self.ensure_redis()
        self.run_step('数据库', [sys.executable, '-m', 'scripts.prepare_db'])
        self.start_child('API', [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host','127.0.0.1',
            '--port',str(self.api_port), '--reload','--reload-dir','app','--reload-dir','config','--reload-dir','utils'], env={'APP_RUNTIME_ROLE':'api'})
        self.wait_ready('API', self.api_url + '/health/live')
        self.start_child('后台', [sys.executable, '-m', 'scripts.run_background_runtime', '--report-ready'], env={'APP_RUNTIME_ROLE':'background'})
        self.start_child('前端', [node, str(vite), '--host','127.0.0.1','--port',str(self.frontend_port),'--strictPort'], cwd=self.root / 'frontend')
        self.wait_ready('前端', self.frontend_url + '/')
        self.wait_ready('完整服务', self.api_url + '/health', needs_background=True)
        self.startup_complete.set()
        self.log.write('就绪', f'前端 {self.frontend_url}  |  API {self.api_url}')
        self.log.write('就绪', f'所有服务的日志汇总在本窗口，完整日志：{self.log.path}')
        self.log.write('操作', '按 Ctrl+C 或 Q 停止全部服务；也可运行 dev_start.bat --stop。关闭窗口会一并结束子进程。')

    def monitor(self):
        while not self.stopped():
            self.check_children()
            if os.name == 'nt' and sys.stdin.isatty():
                import msvcrt
                if msvcrt.kbhit() and msvcrt.getwch().lower() == 'q':
                    return
            self.stop_requested.wait(.3)

    def shutdown(self):
        self.log.write('停止', '正在结束本次启动的服务…')
        for child in reversed(self.children):
            if child.process.poll() is None:
                try:
                    if os.name == 'nt':
                        child.process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        child.process.terminate()
                except OSError:
                    pass
        deadline = time.monotonic() + 8
        while any(c.process.poll() is None for c in self.children) and time.monotonic() < deadline:
            time.sleep(.1)
        self.job.close()
        for child in self.children:
            try:
                child.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.process.kill()
                child.process.wait(timeout=3)
            child.reader.join(timeout=2)
        self.log.write('停止', '本次启动的服务已全部结束。')


def main(argv=None):
    parser = argparse.ArgumentParser(description='OpenTrading 单窗口启动器')
    parser.add_argument('--stop', action='store_true', help='停止当前项目的启动器及其服务')
    parser.add_argument('--startup-timeout', type=int, default=120)
    parser.add_argument('--pause', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--no-pause', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf8', errors='replace')
    if args.stop:
        print('已通知 OpenTrading 停止。' if request_stop(ROOT) else '当前没有由此启动器运行的 OpenTrading。', flush=True)
        return 0
    if sys.version_info[:2] != (3,12):
        print('请使用项目的 Python 3.12 环境启动。', file=sys.stderr)
        return 1
    from config import settings
    lock = LauncherLock(settings.RUNTIME_ROOT_DIR / 'launcher.lock')
    if not lock.acquire():
        print('OpenTrading 启动器已经在运行，请使用现有窗口。需要停止时运行 dev_start.bat --stop。', flush=True)
        return 0
    job, stop_event, log, launcher = None, None, None, None
    try:
        stop_event, job = StopEvent(ROOT), ProcessJob()
        log = SessionLog(settings.RUNTIME_ROOT_DIR / 'launcher')
        launcher = Launcher(root=ROOT, settings=settings, log=log, job=job, stop_event=stop_event, timeout=max(args.startup_timeout,1))
        for name in ('SIGINT','SIGTERM','SIGBREAK'):
            if hasattr(signal,name):
                signal.signal(getattr(signal,name),lambda *_: launcher.stop_requested.set())
        log.write('启动', 'OpenTrading 单窗口启动器')
        launcher.start()
        launcher.monitor()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        if log:
            log.write('失败', str(exc))
        else:
            print(f'启动失败：{exc}', file=sys.stderr)
        return 1
    finally:
        if launcher:
            launcher.shutdown()
        elif job:
            job.close()
        if stop_event:
            stop_event.close()
        if log:
            log.close()
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
