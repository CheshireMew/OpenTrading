from __future__ import annotations

from app.runtime_definition import RuntimeBuildContext, RuntimeServiceDefinition
from app.runtime_refs import INFRA_CACHE_SERVICE, INFRA_DATABASE_RUNTIME, INFRA_EXCHANGE_GATEWAY, INFRA_KLINE_STORE
from config import settings


def _build_database_runtime(_ctx: RuntimeBuildContext):
    from app.infra.db import build_database_runtime

    return build_database_runtime(settings)


def _build_cache_service(_ctx: RuntimeBuildContext):
    from app.infra.cache import build_cache_service

    return build_cache_service(settings)


def _build_exchange_gateway(_ctx: RuntimeBuildContext):
    from app.services.market.exchange_gateway import ExchangeGateway

    return ExchangeGateway(exchange_id=settings.EXCHANGE_ID)


def _build_kline_store(ctx: RuntimeBuildContext):
    from app.infra.persistence.market.kline_store import KlineStore

    return KlineStore(database_runtime=ctx.require(INFRA_DATABASE_RUNTIME))


INFRA_SERVICE_DEFINITIONS: tuple[RuntimeServiceDefinition, ...] = (
    RuntimeServiceDefinition(INFRA_DATABASE_RUNTIME, frozenset({"api", "background"}), _build_database_runtime),
    RuntimeServiceDefinition(INFRA_CACHE_SERVICE, frozenset({"api", "background"}), _build_cache_service),
    RuntimeServiceDefinition(INFRA_EXCHANGE_GATEWAY, frozenset({"api"}), _build_exchange_gateway),
    RuntimeServiceDefinition(
        INFRA_KLINE_STORE,
        frozenset({"api"}),
        _build_kline_store,
        deps=(INFRA_DATABASE_RUNTIME,),
    ),
)
