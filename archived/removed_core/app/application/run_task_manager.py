from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.infra.executor import run_background
from utils.logger import logger


class RunTaskManager:
    def __init__(
        self,
        *,
        list_active_run_ids: Callable[[], list[int]],
        tick: Callable[[int], bool],
        mark_failed: Callable[[int, str], None],
        interval_seconds: Callable[[], float],
        error_label: str,
    ) -> None:
        self._list_active_run_ids = list_active_run_ids
        self._tick = tick
        self._mark_failed = mark_failed
        self._interval_seconds = interval_seconds
        self._error_label = error_label
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._discovery_task: asyncio.Task[Any] | None = None

    async def start_active_run_monitoring(self) -> None:
        await self._reconcile_active_runs(initial_delay=self._interval_seconds())
        if self._discovery_task is None or self._discovery_task.done():
            self._discovery_task = asyncio.create_task(self._discover_active_runs_loop())

    async def shutdown(self) -> None:
        discovery_task = self._discovery_task
        self._discovery_task = None
        if discovery_task is not None:
            discovery_task.cancel()
            await asyncio.gather(discovery_task, return_exceptions=True)

        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def ensure_task(self, run_id: int, *, initial_delay: float = 0.0) -> None:
        task = self._tasks.get(run_id)
        if task and not task.done():
            return
        self._tasks[run_id] = asyncio.create_task(self._run_loop(run_id, initial_delay=initial_delay))

    async def cancel_task(self, run_id: int) -> None:
        task = self._tasks.pop(run_id, None)
        if not task:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _run_loop(self, run_id: int, *, initial_delay: float = 0.0) -> None:
        try:
            if initial_delay > 0:
                await asyncio.sleep(initial_delay)
            while True:
                should_continue = await run_background(lambda: self._tick(run_id))
                if not should_continue:
                    self._tasks.pop(run_id, None)
                    return
                await asyncio.sleep(self._interval_seconds())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await run_background(lambda: self._mark_failed(run_id, str(exc)))
            self._tasks.pop(run_id, None)
            logger.error(f"{self._error_label} run_id={run_id}: {exc}", exc_info=True)

    async def _discover_active_runs_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval_seconds())
                await self._reconcile_active_runs()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"{self._error_label} active-run discovery failed: {exc}", exc_info=True)
            self._discovery_task = None

    async def _reconcile_active_runs(self, *, initial_delay: float = 0.0) -> None:
        run_ids = await run_background(self._list_active_run_ids)
        active_ids = set(run_ids)
        for run_id, task in list(self._tasks.items()):
            if run_id in active_ids or task.done():
                continue
            await self.cancel_task(run_id)
        for run_id in run_ids:
            self.ensure_task(run_id, initial_delay=initial_delay)
