from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TypeVar

from config import settings

T = TypeVar("T")


@dataclass(slots=True)
class BlockingExecutorRuntime:
    database: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(
        max_workers=max(int(settings.BLOCKING_DATABASE_MAX_WORKERS), 1),
        thread_name_prefix="opentrading-db",
    ))
    compute: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(
        max_workers=max(int(settings.BLOCKING_COMPUTE_MAX_WORKERS), 1),
        thread_name_prefix="opentrading-compute",
    ))
    external_io: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(
        max_workers=max(int(settings.BLOCKING_EXTERNAL_IO_MAX_WORKERS), 1),
        thread_name_prefix="opentrading-external",
    ))
    background: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(
        max_workers=max(int(settings.BLOCKING_BACKGROUND_MAX_WORKERS), 1),
        thread_name_prefix="opentrading-background",
    ))
    tools: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(
        max_workers=max(int(settings.BLOCKING_TOOL_MAX_WORKERS), 1),
        thread_name_prefix="opentrading-tools",
    ))

    def shutdown(self) -> None:
        for executor in (self.database, self.compute, self.external_io, self.background, self.tools):
            executor.shutdown(wait=True, cancel_futures=True)


_executor_runtime: BlockingExecutorRuntime | None = None


def _get_executor_runtime() -> BlockingExecutorRuntime:
    global _executor_runtime
    if _executor_runtime is None:
        _executor_runtime = BlockingExecutorRuntime()
    return _executor_runtime


def shutdown_blocking_executors() -> None:
    global _executor_runtime
    if _executor_runtime is None:
        return
    _executor_runtime.shutdown()
    _executor_runtime = None


async def _run(executor: ThreadPoolExecutor, action: Callable[[], T]) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, action)


async def run_database(action: Callable[[], T]) -> T:
    return await _run(_get_executor_runtime().database, action)


async def run_compute(action: Callable[[], T]) -> T:
    return await _run(_get_executor_runtime().compute, action)


async def run_external_io(action: Callable[[], T]) -> T:
    return await _run(_get_executor_runtime().external_io, action)


async def run_background(action: Callable[[], T]) -> T:
    return await _run(_get_executor_runtime().background, action)


async def run_tool(action: Callable[[], T]) -> T:
    return await _run(_get_executor_runtime().tools, action)
