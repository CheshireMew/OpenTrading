from __future__ import annotations

from app.runtime import AppRuntimeServices


async def start_market_scheduler(service, _runtime_services: AppRuntimeServices) -> None:
    service.start()


async def shutdown_service(service, _runtime_services: AppRuntimeServices) -> None:
    await service.shutdown()
