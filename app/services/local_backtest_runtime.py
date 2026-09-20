from __future__ import annotations
import asyncio
import os
import subprocess
import sys
from app.services.local_backtest_service import LocalBacktestService
from app.infra.worker_process import start_worker
from config.settings import BASE_DIR
from utils.logger import logger


class LocalBacktestRuntime:
    def __init__(self, database, workers=2):
        self.service = LocalBacktestService(database)
        self.task = None
        self.tasks = []
        self.workers = max(1, min(4, workers))
        self.processes = {}

    @property
    def process(self):
        """Compatibility for tools inspecting a single-worker runtime."""
        return next(iter(self.processes.values()), None)

    async def start(self):
        if self.tasks:
            return
        await asyncio.to_thread(self.service.repository.interrupt_active)
        self.tasks = [asyncio.create_task(self._loop()) for _ in range(self.workers)]
        self.task = asyncio.gather(*self.tasks, return_exceptions=True)

    async def shutdown(self):
        if self.tasks:
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.tasks = []
            self.task = None

    async def _loop(self):
        while True:
            identifier = None
            process = None
            job = None
            try:
                identifier = await asyncio.to_thread(self.service.repository.claim)
                if identifier is None:
                    await asyncio.sleep(1)
                    continue
                folder = self.service.directory(identifier)
                with (folder / "run.log").open("a", encoding="utf-8") as output:
                    env = {**os.environ, "PYTHONUTF8": "1", "DATABASE_URL": self.service.repository.database.database_url,
                           "RUNTIME_ROOT_DIR": str(folder.parent.parent)}
                    process, job = start_worker([sys.executable, "-m", "scripts.local_backtest_worker", identifier],
                        cwd=BASE_DIR, env=env, stdout=output, stderr=subprocess.STDOUT)
                    self.processes[identifier] = process
                    while process.poll() is None:
                        run = await asyncio.to_thread(self.service.repository.get, identifier)
                        if run["status"] in {"cancelled", "interrupted"}:
                            process.terminate()
                            break
                        await asyncio.sleep(.5)
                    await asyncio.to_thread(process.wait)
                await asyncio.to_thread(self.service.repository.patch, identifier,
                    allowed={"preparing", "running", "saving"}, status="failed", error="回测进程提前退出，请查看运行日志")
            except asyncio.CancelledError:
                if process and process.poll() is None:
                    process.terminate()
                    await asyncio.to_thread(process.wait)
                if identifier:
                    await asyncio.to_thread(self.service.repository.patch, identifier,
                        allowed={"preparing", "running", "saving"}, status="interrupted", error="后台运行时已停止")
                raise
            except Exception:
                logger.exception("本地回测后台执行失败")
                if process and process.poll() is None:
                    process.terminate()
                    await asyncio.to_thread(process.wait)
                if identifier:
                    await asyncio.to_thread(self.service.repository.patch, identifier,
                        allowed={"preparing", "running", "saving"}, status="failed", error="后台调度失败，请查看后台日志")
                await asyncio.sleep(2)
            finally:
                self.processes.pop(identifier, None)
                if job:
                    job.close()
