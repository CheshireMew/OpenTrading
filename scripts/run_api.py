"""Uvicorn development server in a console isolated by dev_launcher."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import signal
import sys

import uvicorn
from uvicorn._subprocess import get_subprocess
from uvicorn.supervisors.statreload import StatReload


class ConsoleReload(StatReload):
    def restart(self):
        if os.name != 'nt':
            return super().restart()
        # CTRL_C_EVENT cannot target the worker's PID as a process group.
        # This console contains only the API reloader and its descendants.
        self.mtimes.clear()
        self.is_restarting = True
        os.kill(0, signal.CTRL_C_EVENT)
        sys.stdout.write(' ')
        sys.stdout.flush()
        self.process.join()
        if not self.should_exit.is_set():
            self.process = get_subprocess(config=self.config, target=self.target, sockets=self.sockets)
            self.process.start()


def require_isolated_console(launcher_pid):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetConsoleProcessList.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    members = (wintypes.DWORD * 64)()
    count = api.GetConsoleProcessList(members, len(members))
    if not count or count > len(members) or launcher_pid in members[:count]:
        raise RuntimeError('API 热重载必须由启动器在独立控制台中启动。')


def main():
    parser = argparse.ArgumentParser(description='OpenTrading API development process')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--launcher-pid', type=int, required=True)
    args = parser.parse_args()
    if os.name == 'nt':
        require_isolated_console(args.launcher_pid)
    sys.path.insert(0, str(Path.cwd()))
    config = uvicorn.Config('app.main:app', host='127.0.0.1', port=args.port,
                            reload=True, reload_dirs=['app', 'config', 'utils'])
    server = uvicorn.Server(config)
    sock = config.bind_socket()
    try:
        ConsoleReload(config, target=server.run, sockets=[sock]).run()
    finally:
        sock.close()


if __name__ == '__main__':
    main()
