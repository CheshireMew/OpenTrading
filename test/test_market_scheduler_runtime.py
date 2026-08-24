import pytest

from app.services.market_scheduler_runtime import MarketSchedulerRuntime


@pytest.mark.asyncio
async def test_scheduler_start_runs_first_collection_immediately(monkeypatch):
    runtime = MarketSchedulerRuntime(indicator_repository=object(), cleanup_old_data=lambda: None)
    calls: list[str] = []

    async def record_indicator_job():
        calls.append("indicator")

    async def record_cleanup_job():
        calls.append("cleanup")

    monkeypatch.setattr(runtime, "_run_market_indicator_job", record_indicator_job)
    monkeypatch.setattr(runtime, "_cleanup_old_data", record_cleanup_job)

    await runtime.start()

    try:
        assert calls == ["indicator"]
        assert {job.id for job in runtime.scheduler.get_jobs()} == {
            "fetch_market_indicators",
            "data_retention_cleanup",
        }
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_scheduler_start_fails_when_first_collection_fails(monkeypatch):
    runtime = MarketSchedulerRuntime(indicator_repository=object(), cleanup_old_data=lambda: None)

    async def fail_indicator_job():
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(runtime, "_run_market_indicator_job", fail_indicator_job)

    with pytest.raises(RuntimeError, match="upstream unavailable"):
        await runtime.start()

    await runtime.shutdown()
