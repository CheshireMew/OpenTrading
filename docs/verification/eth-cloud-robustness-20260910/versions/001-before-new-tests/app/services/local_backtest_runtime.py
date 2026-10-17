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
    def __init__(self, database):
        self.service = LocalBacktestService(database)
        self.task = None
        self.process = None

    async def start(self):
        await asyncio.to_thread(self.service.repository.interrupt_active)
        self.task = asyncio.create_task(self._loop(), name="local-backtests")

    async def shutdown(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def _loop(self):
        while True:
            identifier = None
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
                    self.process, job = start_worker([sys.executable, "-m", "scripts.local_backtest_worker", identifier],
                        cwd=BASE_DIR, env=env, stdout=output, stderr=subprocess.STDOUT)
                    while self.process.poll() is None:
                        run = await asyncio.to_thread(self.service.repository.get, identifier)
                        if run["status"] in {"cancelled", "interrupted"}:
                            self.process.terminate()
                            break
                        await asyncio.sleep(.5)
                    await asyncio.to_thread(self.process.wait)
                await asyncio.to_thread(self.service.repository.patch, identifier,
                    allowed={"preparing", "running"}, status="failed", error="回测进程提前退出，请查看运行日志")
            except asyncio.CancelledError:
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    await asyncio.to_thread(self.process.wait)
                if identifier:
                    await asyncio.to_thread(self.service.repository.patch, identifier,
                        allowed={"preparing", "running"}, status="interrupted", error="后台运行时已停止")
                raise
            except Exception:
                logger.exception("本地回测后台执行失败")
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    await asyncio.to_thread(self.process.wait)
                if identifier:
                    await asyncio.to_thread(self.service.repository.patch, identifier,
                        allowed={"preparing", "running"}, status="failed", error="后台调度失败，请查看后台日志")
                await asyncio.sleep(2)
            finally:
                if job:
                    job.close()
                self.process = None
