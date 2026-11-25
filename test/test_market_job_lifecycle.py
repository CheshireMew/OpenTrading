from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.operations import OperationRepository
from app.services.market.history_jobs import JobScheduler
from config import settings
from config.market_data import MarketDataConfig
from scripts.market_data_cli import app as cli


@pytest.fixture
def expired_job(installed_database_runtime, monkeypatch):
    runtime = installed_database_runtime
    monkeypatch.setattr(settings, "DATABASE_URL", runtime.database_url)
    config = MarketDataConfig.load()
    operations = OperationRepository(MarketHistoryDatabase(config.data_dir, engine=runtime.engine))
    past = datetime.now(timezone.utc) - timedelta(days=2)
    operations.create_job(job_id="expired", task="liquidity_refresh", interval_minutes=60, created_at=past)
    # The producer uses its wall clock for the actual lease, independently
    # of the scheduled timestamp. Produce a genuine old lease under that clock.
    import app.infra.persistence.market.history.operations as operation_module

    class PastClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return past if tz else past.replace(tzinfo=None)

    with monkeypatch.context() as clock:
        clock.setattr(operation_module, "datetime", PastClock)
        run = operations.claim_manual("expired", now=past, worker_id="previous-worker", lease_seconds=1)
    operations.set_enabled("expired", False, changed_at=past)
    yield config, operations, run["run_id"]


def test_jobs_status_and_scheduler_construction_do_not_recover(expired_job):
    config, operations, run_id = expired_job
    before = operations.events(correlation_id=run_id)

    result = CliRunner().invoke(cli, ["jobs", "status"])

    assert result.exit_code == 0, result.output
    assert "running" in result.output
    scheduler = JobScheduler(config, operations.database)
    assert scheduler.latest("expired").status == "running"
    assert operations.events(correlation_id=run_id) == before


def test_run_due_recovers_expired_even_without_due_jobs(expired_job):
    config, operations, run_id = expired_job
    scheduler = JobScheduler(config, operations.database)
    assert scheduler.run_due() == ()
    assert scheduler.latest("expired").status == "interrupted"
    events = operations.events(correlation_id=run_id)
    assert sum(event["event"] == "job_recovery" for event in events) == 1
    scheduler.run_due()
    assert operations.events(correlation_id=run_id) == events


def test_manual_execution_recovers_then_persists_its_own_result(expired_job, monkeypatch):
    import app.services.market.history_jobs as jobs

    config, operations, run_id = expired_job
    monkeypatch.setattr(jobs, "sync_liquidity_data", lambda *args: {"series_count": 2, "row_count": 3, "retrieved_at": "offline-fixture"})
    scheduler = JobScheduler(config, operations.database)
    result = scheduler.run("expired")
    assert result.run_id != run_id
    assert result.status == "success"
    assert scheduler.latest("expired").run_id == result.run_id
    assert any(event["event"] == "job_recovery" for event in operations.events(correlation_id=run_id))
    assert any(event["result"] == "success" for event in operations.events(correlation_id=result.run_id))
