import asyncio
import pytest

from app.services.periodic_task import PeriodicTask


@pytest.mark.asyncio
async def test_periodic_start_is_idempotent_and_shutdown_cancels_inflight_work():
    entered, cancelled = asyncio.Event(), asyncio.Event()
    calls = 0

    async def action():
        nonlocal calls
        calls += 1
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = PeriodicTask("test", action, lambda: 10)
    await task.start()
    await task.start()
    await asyncio.wait_for(entered.wait(), 1)
    await task.shutdown()
    await task.shutdown()
    assert cancelled.is_set() and calls == 1


@pytest.mark.asyncio
async def test_failed_cycle_retries_and_task_can_restart_after_shutdown():
    done = asyncio.Event()
    calls = 0

    async def action():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("retry")
        done.set()

    task = PeriodicTask("test", action, lambda: 0.001)
    await task.start()
    await asyncio.wait_for(done.wait(), 1)
    await task.shutdown()
    before = calls
    done.clear()
    await task.start()
    await asyncio.wait_for(done.wait(), 1)
    await task.shutdown()
    assert calls > before
