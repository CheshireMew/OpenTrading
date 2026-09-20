from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.runtime import AppRuntimeServices, RuntimeRole, runtime_role_has_target
from config import settings
from utils.logger import logger
from app.infra.persistence.runtime_status_repository import BACKGROUND_COMPONENT


class BackgroundRuntimeStatus(str, Enum):
    DISABLED = "disabled"
    STANDBY = "standby"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"


class _ProcessFileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        try:
            # 后台任务只能有一个进程持有。这里不用轮询等待，拿不到就直接退回 standby，
            # 避免 API worker 因抢不到后台职责而阻塞启动。
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


@dataclass(slots=True)
class BackgroundRuntimeState:
    status: BackgroundRuntimeStatus
    owner: bool = False
    error: Exception | None = None


class BackgroundRuntimeController:
    def __init__(self, runtime_services: AppRuntimeServices, *, role: RuntimeRole | None = None) -> None:
        self.runtime_services = runtime_services
        self.role = role or settings.APP_RUNTIME_ROLE
        self._lock = _ProcessFileLock(settings.BACKGROUND_RUNTIME_LOCK_PATH)
        self._state = BackgroundRuntimeState(status=BackgroundRuntimeStatus.DISABLED)
        self._startup_task: asyncio.Task[None] | None = None
        self._owner_id = f"{os.getpid()}-{uuid.uuid4().hex}"
        from app.services.local_backtest_runtime import LocalBacktestRuntime
        self._local_backtests = LocalBacktestRuntime(runtime_services.infra.database_runtime)

    @property
    def state(self) -> BackgroundRuntimeState:
        return self._state

    def should_run(self) -> bool:
        return runtime_role_has_target(self.role, "background")

    async def start(self) -> None:
        if not self.should_run():
            self._state = BackgroundRuntimeState(status=BackgroundRuntimeStatus.DISABLED, owner=False)
            return

        acquired = await asyncio.to_thread(self._lock.acquire)
        if not acquired:
            self._state = BackgroundRuntimeState(status=BackgroundRuntimeStatus.STANDBY, owner=False)
            return

        self._state = BackgroundRuntimeState(status=BackgroundRuntimeStatus.STARTING, owner=True)
        runtime_status = self.runtime_services.infra.runtime_status
        if runtime_status is not None:
            await asyncio.to_thread(
                runtime_status.mark_starting,
                BACKGROUND_COMPONENT,
                self._owner_id,
            )
        self._startup_task = asyncio.create_task(self._bootstrap(), name="background-runtime-startup")

    async def wait_until_started(self) -> None:
        if self._startup_task is not None:
            await self._startup_task

    async def shutdown(self) -> None:
        startup_task = self._startup_task
        self._startup_task = None
        if startup_task is not None and not startup_task.done():
            startup_task.cancel()
            await asyncio.gather(startup_task, return_exceptions=True)

        if self._state.owner:
            await self._shutdown_runtime_services()
            runtime_status = self.runtime_services.infra.runtime_status
            if runtime_status is not None:
                await asyncio.to_thread(
                    runtime_status.mark_stopped,
                    BACKGROUND_COMPONENT,
                    self._owner_id,
                )
        await asyncio.to_thread(self._lock.release)
        if self._state.status != BackgroundRuntimeStatus.FAILED:
            self._state = BackgroundRuntimeState(status=BackgroundRuntimeStatus.DISABLED, owner=False)

    async def _bootstrap(self) -> None:
        try:
            await self.runtime_services.require_background().market_scheduler.start(self._owner_id)
            await self._local_backtests.start()
            runtime_status = self.runtime_services.infra.runtime_status
            if runtime_status is not None:
                await asyncio.to_thread(
                    runtime_status.mark_ready,
                    BACKGROUND_COMPONENT,
                    self._owner_id,
                )
            self._state = BackgroundRuntimeState(status=BackgroundRuntimeStatus.READY, owner=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._shutdown_runtime_services()
            runtime_status = self.runtime_services.infra.runtime_status
            if runtime_status is not None:
                await asyncio.to_thread(
                    runtime_status.mark_failed,
                    BACKGROUND_COMPONENT,
                    self._owner_id,
                    error_code="startup_failed",
                    error_detail=str(exc),
                )
            self._state = BackgroundRuntimeState(status=BackgroundRuntimeStatus.FAILED, owner=True, error=exc)
            logger.error(f"后台运行时启动失败: {exc}", exc_info=True)

    async def _shutdown_runtime_services(self) -> None:
        await self._local_backtests.shutdown()
        if self.runtime_services.background is not None:
            await self.runtime_services.background.market_scheduler.shutdown()
