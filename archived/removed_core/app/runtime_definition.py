from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.runtime import AppRuntimeServices, RuntimeRole, RuntimeTarget
from app.runtime_refs import RuntimeServiceRef


BackgroundLifecycleRunner = Callable[[Any, AppRuntimeServices], Awaitable[None] | None]
RuntimeFactory = Callable[["RuntimeBuildContext"], Any]


@dataclass(frozen=True, slots=True)
class RuntimeServiceDefinition:
    ref: RuntimeServiceRef
    targets: frozenset[RuntimeTarget]
    build: RuntimeFactory
    deps: tuple[RuntimeServiceRef, ...] = ()
    optional_deps: tuple[RuntimeServiceRef, ...] = ()
    background_start: BackgroundLifecycleRunner | None = None
    background_stop: BackgroundLifecycleRunner | None = None
    background_start_order: int = 0
    background_stop_order: int = 0


@dataclass(slots=True)
class RuntimeBuildContext:
    role: RuntimeRole
    services: AppRuntimeServices

    def require(self, ref: RuntimeServiceRef):
        return self.services.require_service(ref)

    def optional(self, ref: RuntimeServiceRef):
        return self.services.get_service(ref)
