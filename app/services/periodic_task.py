"""A cancellable, single-owner periodic task; evaluation policy stays with its caller."""

import asyncio
from collections.abc import Awaitable, Callable

from utils.logger import logger


class PeriodicTask:
    def __init__(self, name: str, action: Callable[[], Awaitable[object]], interval: Callable[[], float]):
        self._name = name
        self._action = action
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._lifecycle_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._run(), name=self._name)

    async def shutdown(self) -> None:
        async with self._lifecycle_lock:
            task, self._task = self._task, None
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        while True:
            try:
                await self._action()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s evaluation cycle failed", self._name)
            await asyncio.sleep(max(float(self._interval()), 0.001))
