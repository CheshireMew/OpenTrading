from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime
from sqlalchemy import event

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import Base
from app.infra.persistence.runtime_status_repository import (
    BACKGROUND_COMPONENT,
    MARKET_INDICATORS_COMPONENT,
    RuntimeStatusRepository,
)
from app.lifecycle import build_health_payload
from app.runtime import AppRuntimeServices, IndicatorRuntimeServices, InfraRuntimeServices


def _app_with_repository(repository):
    runtime_services = AppRuntimeServices(
        infra=InfraRuntimeServices(object(), object(), repository),
        indicators=IndicatorRuntimeServices(object(), object()),
    )
    return SimpleNamespace(
        state=SimpleNamespace(
            runtime_services=runtime_services,
            background_services_task=None,
            background_services_error=None,
            background_runtime=None,
        )
    )


def test_product_health_uses_cross_process_heartbeat(tmp_path):
    runtime = DatabaseRuntime(
        database_url=f"sqlite:///{(tmp_path / 'health.db').as_posix()}",
        source="test",
    )
    Base.metadata.create_all(runtime.engine)
    repository = RuntimeStatusRepository(runtime)
    repository.mark_starting(BACKGROUND_COMPONENT, "worker-1")
    repository.mark_ready(BACKGROUND_COMPONENT, "worker-1")
    repository.mark_running(MARKET_INDICATORS_COMPONENT, "worker-1")
    repository.mark_success(MARKET_INDICATORS_COMPONENT, "worker-1")
    repository.mark_running(MARKET_INDICATORS_COMPONENT, "worker-1")

    status_selects = 0

    def count_status_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal status_selects
        normalized = statement.upper()
        if normalized.lstrip().startswith("SELECT") and "RUNTIME_COMPONENT_STATUS" in normalized:
            status_selects += 1

    event.listen(runtime.engine, "before_cursor_execute", count_status_selects)
    try:
        payload, status_code = build_health_payload(_app_with_repository(repository))
    finally:
        event.remove(runtime.engine, "before_cursor_execute", count_status_selects)

    assert status_code == 200
    assert payload["status"] == "healthy"
    assert payload["components"]["background_runtime"]["status"] == "ready"
    assert payload["components"]["market_indicators"]["status"] == "running"
    assert status_selects == 1
    runtime.dispose()


def test_product_health_rejects_worker_before_first_collection(tmp_path):
    runtime = DatabaseRuntime(
        database_url=f"sqlite:///{(tmp_path / 'not-ready.db').as_posix()}",
        source="test",
    )
    Base.metadata.create_all(runtime.engine)
    repository = RuntimeStatusRepository(runtime)
    repository.mark_starting(BACKGROUND_COMPONENT, "worker-1")
    repository.mark_ready(BACKGROUND_COMPONENT, "worker-1")
    repository.mark_running(MARKET_INDICATORS_COMPONENT, "worker-1")

    payload, status_code = build_health_payload(_app_with_repository(repository))

    assert status_code == 503
    assert payload["detail"] == "Initial market indicator collection has not succeeded"
    runtime.dispose()


def test_product_health_includes_binance_snapshot_readiness(tmp_path):
    runtime = DatabaseRuntime(
        database_url=f"sqlite:///{(tmp_path / 'binance-health.db').as_posix()}",
        source="test",
    )
    Base.metadata.create_all(runtime.engine)
    repository = RuntimeStatusRepository(runtime)
    repository.mark_starting(BACKGROUND_COMPONENT, "worker-1")
    repository.mark_ready(BACKGROUND_COMPONENT, "worker-1")
    repository.mark_running(MARKET_INDICATORS_COMPONENT, "worker-1")
    repository.mark_success(MARKET_INDICATORS_COMPONENT, "worker-1")

    app = _app_with_repository(repository)
    snapshot = SimpleNamespace(
        health_snapshot=lambda: {"status": "starting", "seedCompleted": False}
    )
    app.state.runtime_services.api = SimpleNamespace(
        market=SimpleNamespace(binance_snapshot=snapshot)
    )

    payload, status_code = build_health_payload(app)

    assert status_code == 503
    assert payload["components"]["binance_market_snapshot"]["status"] == "starting"
    runtime.dispose()


def test_liveness_remains_available_before_worker_starts(tmp_path):
    runtime = DatabaseRuntime(
        database_url=f"sqlite:///{(tmp_path / 'live.db').as_posix()}",
        source="test",
    )
    Base.metadata.create_all(runtime.engine)
    repository = RuntimeStatusRepository(runtime)
    app = _app_with_repository(repository)

    product_payload, product_status = build_health_payload(app)
    live_payload, live_status = build_health_payload(app, include_background=False)

    assert product_status == 503
    assert product_payload["components"]["background_runtime"] == "missing"
    assert live_status == 200
    assert live_payload["components"] == {"database": "ready"}
    runtime.dispose()


def test_market_run_preserves_previous_outcome_across_worker_restart(tmp_path):
    runtime = DatabaseRuntime(
        database_url=f"sqlite:///{(tmp_path / 'history.db').as_posix()}",
        source="test",
    )
    Base.metadata.create_all(runtime.engine)
    repository = RuntimeStatusRepository(runtime)
    repository.mark_running(MARKET_INDICATORS_COMPONENT, "worker-1")
    repository.mark_success(MARKET_INDICATORS_COMPONENT, "worker-1")
    first_success = repository.get(MARKET_INDICATORS_COMPONENT).last_success_at

    repository.mark_running(
        MARKET_INDICATORS_COMPONENT,
        "worker-2",
        next_run_at=datetime(2026, 8, 24),
    )
    snapshot = repository.get(MARKET_INDICATORS_COMPONENT)

    assert snapshot.owner_id == "worker-2"
    assert snapshot.status == "running"
    assert snapshot.last_success_at == first_success
    runtime.dispose()
