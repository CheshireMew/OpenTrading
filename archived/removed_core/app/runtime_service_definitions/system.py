from __future__ import annotations

from app.runtime_definition import RuntimeBuildContext, RuntimeServiceDefinition
from app.runtime_lifecycle import shutdown_service, start_market_scheduler
from app.runtime_refs import (
    INFRA_DATABASE_RUNTIME,
    MARKET_DLI_CACHE,
    MARKET_INDICATOR_REPOSITORY,
    SYSTEM_CURRENCY_RATE_SERVICE,
    SYSTEM_FRED_API_CONFIG_SERVICE,
    SYSTEM_LLM_CONFIG_SERVICE,
    SYSTEM_MARKET_SCHEDULER_RUNTIME,
)


def _build_currency_rate_service(_ctx: RuntimeBuildContext):
    from app.services.currency_service import CurrencyRateService

    return CurrencyRateService()


def _build_llm_config_service(_ctx: RuntimeBuildContext):
    from app.services.llm_config_service import LlmConfigService

    return LlmConfigService()


def _build_fred_api_config_service(_ctx: RuntimeBuildContext):
    from app.services.fred_api_config_service import FredApiConfigService

    return FredApiConfigService()


def _build_market_scheduler_runtime(ctx: RuntimeBuildContext):
    from app.services.market_scheduler_runtime import MarketSchedulerRuntime
    from app.infra.persistence.data_retention import cleanup_old_data

    return MarketSchedulerRuntime(
        indicator_repository=ctx.require(MARKET_INDICATOR_REPOSITORY),
        cleanup_old_data=lambda: cleanup_old_data(ctx.require(INFRA_DATABASE_RUNTIME)),
        dli_cache=ctx.require(MARKET_DLI_CACHE),
    )


SYSTEM_SERVICE_DEFINITIONS: tuple[RuntimeServiceDefinition, ...] = (
    RuntimeServiceDefinition(SYSTEM_CURRENCY_RATE_SERVICE, frozenset({"api"}), _build_currency_rate_service),
    RuntimeServiceDefinition(SYSTEM_LLM_CONFIG_SERVICE, frozenset({"api"}), _build_llm_config_service),
    RuntimeServiceDefinition(SYSTEM_FRED_API_CONFIG_SERVICE, frozenset({"api"}), _build_fred_api_config_service),
    RuntimeServiceDefinition(
        SYSTEM_MARKET_SCHEDULER_RUNTIME,
        frozenset({"background"}),
        _build_market_scheduler_runtime,
        deps=(INFRA_DATABASE_RUNTIME, MARKET_INDICATOR_REPOSITORY, MARKET_DLI_CACHE),
        background_start=start_market_scheduler,
        background_stop=shutdown_service,
        background_start_order=10,
        background_stop_order=40,
    ),
)
