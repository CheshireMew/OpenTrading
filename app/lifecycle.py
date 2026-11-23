from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.background_runtime import BackgroundRuntimeController, BackgroundRuntimeStatus
from app.product import APP_VERSION
from app.runtime import AppRuntimeServices, RuntimeRole, runtime_role_has_target
from app.runtime import build_app_runtime_services
from config import settings
from utils.logger import logger
from app.infra.persistence.runtime_status_repository import (
    BACKGROUND_COMPONENT,
    MARKET_INDICATORS_COMPONENT,
)


def _init_db(database_runtime) -> None:
    from app.infra.db.schema_runtime import verify_database_schema

    verify_database_schema(database_runtime)


async def _init_db_async(app) -> None:
    database_runtime = app.state.runtime_services.infra.database_runtime
    await asyncio.to_thread(_init_db, database_runtime)


async def _start_background_services(app, runtime_services: AppRuntimeServices) -> None:
    try:
        role: RuntimeRole = getattr(app.state, "runtime_role", None) or settings.APP_RUNTIME_ROLE
        background_runtime = BackgroundRuntimeController(runtime_services, role=role)
        app.state.background_runtime = background_runtime
        await background_runtime.start()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        app.state.background_services_error = exc
        logger.error(f"后台服务启动失败: {exc}", exc_info=True)


async def _shutdown_background_services(app) -> None:
    background_runtime = getattr(app.state, "background_runtime", None)
    if background_runtime is not None:
        await background_runtime.shutdown()


async def _shutdown_runtime_services(app) -> None:
    runtime_services = getattr(app.state, "runtime_services", None)
    if runtime_services is not None:
        await runtime_services.shutdown()


async def _cancel_task(task: asyncio.Task | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@asynccontextmanager
async def lifespan(app):
    role: RuntimeRole = getattr(app.state, "runtime_role", None) or settings.APP_RUNTIME_ROLE
    app.state.background_services_error = None
    app.state.background_runtime = None
    app.state.runtime_services = await asyncio.to_thread(build_app_runtime_services, role)
    app.state.background_services_task = None
    try:
        await _init_db_async(app)
        await app.state.runtime_services.start()
        app.state.background_services_task = (
            asyncio.create_task(_start_background_services(app, app.state.runtime_services))
            if runtime_role_has_target(role, "background")
            else None
        )
        yield
    finally:
        await _cancel_task(getattr(app.state, "background_services_task", None))
        await _shutdown_background_services(app)
        await _shutdown_runtime_services(app)


def build_health_payload(app, *, include_background: bool = True) -> tuple[dict[str, object], int]:
    background_services_task = getattr(app.state, "background_services_task", None)
    background_services_error = getattr(app.state, "background_services_error", None)
    background_runtime = getattr(app.state, "background_runtime", None)
    background_runtime_state = (
        background_runtime.state if background_runtime is not None else None
    )

    background_component = "disabled"
    if background_runtime_state is not None:
        background_component = background_runtime_state.status.value
    elif background_services_task is not None and not background_services_task.done():
        background_component = "starting"

    components: dict[str, object] = {
        "database": "ready",
        "background_runtime": background_component,
    }

    def response(status: str, status_code: int, detail: str | None = None) -> tuple[dict[str, object], int]:
        payload: dict[str, object] = {
            "status": status,
            "version": APP_VERSION,
            "components": components,
        }
        if detail is not None:
            payload["detail"] = detail
        return payload, status_code

    if not include_background:
        components = {"database": "ready"}
        return response("healthy", 200)

    runtime_services = getattr(app.state, "runtime_services", None)
    api_runtime = getattr(runtime_services, "api", None) if runtime_services is not None else None
    market_runtime = getattr(api_runtime, "market", None) if api_runtime is not None else None
    binance_snapshot = getattr(market_runtime, "binance_snapshot", None) if market_runtime is not None else None
    binance_health = (
        binance_snapshot.health_snapshot()
        if binance_snapshot is not None and hasattr(binance_snapshot, "health_snapshot")
        else None
    )
    if binance_health is not None:
        components["binance_market_snapshot"] = binance_health
    runtime_status = (
        runtime_services.infra.runtime_status
        if runtime_services is not None
        else None
    )
    if runtime_status is not None:
        status_by_component = runtime_status.get_many(
            (BACKGROUND_COMPONENT, MARKET_INDICATORS_COMPONENT)
        )
        worker = status_by_component.get(BACKGROUND_COMPONENT)
        indicators = status_by_component.get(MARKET_INDICATORS_COMPONENT)
        if worker is None:
            components["background_runtime"] = "missing"
            return response("unhealthy", 503, "Background worker has not reported readiness")

        age_seconds = max(
            0.0,
            (
                datetime.now(timezone.utc).replace(tzinfo=None)
                - worker.heartbeat_at
            ).total_seconds(),
        )
        components["background_runtime"] = {
            "status": worker.status,
            "heartbeatAgeSeconds": round(age_seconds, 3),
        }
        if indicators is not None:
            components["market_indicators"] = {
                "status": indicators.status,
                "lastSuccessAt": indicators.last_success_at.isoformat() if indicators.last_success_at else None,
                "lastFailureAt": indicators.last_failure_at.isoformat() if indicators.last_failure_at else None,
                "nextRunAt": indicators.next_run_at.isoformat() if indicators.next_run_at else None,
                "errorCode": indicators.error_code,
            }
        if worker.status != "ready" or age_seconds > settings.BACKGROUND_HEARTBEAT_STALE_SECONDS:
            return response("unhealthy", 503, "Background worker is not ready or its heartbeat is stale")
        if (
            indicators is None
            or indicators.last_success_at is None
            or indicators.status not in {"ready", "running"}
        ):
            return response("unhealthy", 503, "Initial market indicator collection has not succeeded")

    if binance_health is not None and binance_health["status"] != "ready":
        return response("unhealthy", 503, "Binance market snapshot is not ready")

    if background_services_error is not None:
        return response("unhealthy", 503, "Background services failed")
    if (
        background_runtime_state is not None
        and background_runtime_state.status == BackgroundRuntimeStatus.FAILED
    ):
        return response("unhealthy", 503, "Background runtime failed")
    return response("healthy", 200)
