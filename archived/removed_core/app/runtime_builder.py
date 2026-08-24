from __future__ import annotations

from app.runtime import AppRuntimeServices, RuntimeRole, runtime_role_targets
from app.runtime_definition import RuntimeBuildContext, RuntimeServiceDefinition
from app.runtime_service_definitions import RUNTIME_SERVICE_DEFINITIONS
from config import settings


def active_service_definitions(role: RuntimeRole) -> tuple[RuntimeServiceDefinition, ...]:
    active_targets = set(runtime_role_targets(role))
    return tuple(
        definition
        for definition in RUNTIME_SERVICE_DEFINITIONS
        if definition.targets & active_targets
    )


def _topologically_sorted_service_definitions(
    definitions: tuple[RuntimeServiceDefinition, ...],
) -> list[RuntimeServiceDefinition]:
    remaining = {definition.ref: definition for definition in definitions}
    active_refs = set(remaining)
    ordered: list[RuntimeServiceDefinition] = []

    missing_required_edges = [
        f"{definition.ref.key} -> {dependency.key}"
        for definition in definitions
        for dependency in definition.deps
        if dependency not in active_refs
    ]
    if missing_required_edges:
        raise RuntimeError(
            "Runtime service graph has inactive required dependencies: "
            + ", ".join(sorted(missing_required_edges))
        )

    while remaining:
        ready = sorted(
            (
                definition
                for definition in remaining.values()
                if all(
                    dep not in remaining
                    for dep in definition.deps
                    + tuple(dep for dep in definition.optional_deps if dep in active_refs)
                )
            ),
            key=lambda definition: definition.ref.key,
        )
        if not ready:
            cycle = ", ".join(sorted(ref.key for ref in remaining))
            raise RuntimeError(f"Runtime service graph contains a cycle: {cycle}")
        for definition in ready:
            ordered.append(definition)
            remaining.pop(definition.ref, None)
    return ordered


def build_app_runtime_services(role: RuntimeRole | None = None) -> AppRuntimeServices:
    resolved_role = role or settings.APP_RUNTIME_ROLE
    services = AppRuntimeServices.empty()
    context = RuntimeBuildContext(role=resolved_role, services=services)
    definitions = active_service_definitions(resolved_role)

    for definition in _topologically_sorted_service_definitions(definitions):
        services.set_service(definition.ref, definition.build(context))

    validate_runtime_services(services, resolved_role)
    return services


def missing_required_services(services: AppRuntimeServices, role: RuntimeRole = "all") -> list[str]:
    return [
        definition.ref.key
        for definition in active_service_definitions(role)
        if services.get_service(definition.ref) is None
    ]


def validate_runtime_services(services: AppRuntimeServices, role: RuntimeRole = "all") -> None:
    missing = missing_required_services(services, role)
    if missing:
        raise RuntimeError(f"Runtime services missing: {', '.join(missing)}")


def background_start_definitions() -> tuple[RuntimeServiceDefinition, ...]:
    return tuple(
        sorted(
            (
                definition
                for definition in active_service_definitions("background")
                if definition.background_start is not None
            ),
            key=lambda definition: (definition.background_start_order, definition.ref.key),
        )
    )


def background_stop_definitions() -> tuple[RuntimeServiceDefinition, ...]:
    return tuple(
        sorted(
            (
                definition
                for definition in active_service_definitions("background")
                if definition.background_stop is not None
            ),
            key=lambda definition: (definition.background_stop_order, definition.ref.key),
        )
    )
