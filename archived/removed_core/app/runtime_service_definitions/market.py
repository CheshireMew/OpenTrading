from __future__ import annotations

from typing import Any, Callable

from app.runtime_definition import RuntimeBuildContext, RuntimeServiceDefinition
from app.runtime_refs import (
    INFRA_CACHE_SERVICE,
    INFRA_DATABASE_RUNTIME,
    INFRA_EXCHANGE_GATEWAY,
    INFRA_KLINE_STORE,
    MARKET_BINANCE_MARKET_INTEL,
    MARKET_BINANCE_MARKET_RESEARCH_STORE,
    MARKET_BINANCE_MARKET_SNAPSHOT,
    MARKET_BINANCE_WEB3_HEAT_RANKS,
    MARKET_BINANCE_WEB3_RANKS,
    MARKET_BINANCE_WEB3_TOKENS,
    MARKET_DLI_CACHE,
    MARKET_FUNDING_RATE_APP_SERVICE,
    MARKET_FUNDING_RATE_SERVICE,
    MARKET_FUNDING_RATE_STORE,
    MARKET_INDEX_DATA_SERVICE,
    MARKET_INDICATOR_REPOSITORY,
    MARKET_INDICATOR_SERVICE,
    MARKET_INSIGHT_APP_SERVICE,
    MARKET_MARKET_DATA_SERVICE,
    MARKET_QUERY_APP_SERVICE,
    MARKET_REALTIME_SERVICE,
    MARKET_WEBSOCKET_SERVICE,
    SYSTEM_LLM_CONFIG_SERVICE,
)


def _build_llm_client_factory(llm_config_service) -> Callable[[], Any]:
    from app.infra.llm_client import LLMClient

    return lambda: LLMClient(llm_config=llm_config_service.read_effective_config())


def _build_market_data_service(ctx: RuntimeBuildContext):
    from app.services.market.market_data_service import MarketDataService

    return MarketDataService(
        exchange_gateway=ctx.require(INFRA_EXCHANGE_GATEWAY),
        kline_store=ctx.require(INFRA_KLINE_STORE),
        cache_service=ctx.require(INFRA_CACHE_SERVICE),
    )


def _build_realtime_service(_ctx: RuntimeBuildContext):
    from app.services.market.realtime_service import RealtimeService

    return RealtimeService()


def _build_market_indicator_repository(ctx: RuntimeBuildContext):
    from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository

    return MarketIndicatorRepository(database_runtime=ctx.require(INFRA_DATABASE_RUNTIME))


def _build_indicator_service(ctx: RuntimeBuildContext):
    from app.services.market.indicator_service import IndicatorService

    return IndicatorService(
        repository=ctx.require(MARKET_INDICATOR_REPOSITORY),
        dli_cache=ctx.require(MARKET_DLI_CACHE),
    )


def _build_dli_cache(ctx: RuntimeBuildContext):
    from app.services.market.dli_cache import DliLiquidityCache

    return DliLiquidityCache(cache_service=ctx.require(INFRA_CACHE_SERVICE))


def _build_funding_rate_store(ctx: RuntimeBuildContext):
    from app.infra.persistence.market.funding_rate_store import FundingRateStore

    return FundingRateStore(database_runtime=ctx.require(INFRA_DATABASE_RUNTIME))


def _build_funding_rate_service(ctx: RuntimeBuildContext):
    from app.services.market.funding_rate_service import FundingRateService

    return FundingRateService(store=ctx.require(MARKET_FUNDING_RATE_STORE))


def _build_funding_rate_app_service(ctx: RuntimeBuildContext):
    from app.services.market.funding_rate_app_service import FundingRateAppService

    return FundingRateAppService(funding_rate_service=ctx.require(MARKET_FUNDING_RATE_SERVICE))


def _build_market_query_app_service(ctx: RuntimeBuildContext):
    from app.services.market.query_app_service import MarketQueryAppService

    return MarketQueryAppService(
        market_data_service=ctx.require(MARKET_MARKET_DATA_SERVICE),
        realtime_service=ctx.require(MARKET_REALTIME_SERVICE),
        binance_snapshot_service=ctx.require(MARKET_BINANCE_MARKET_SNAPSHOT),
        llm_client_factory=_build_llm_client_factory(ctx.require(SYSTEM_LLM_CONFIG_SERVICE)),
    )


def _build_market_insight_app_service(ctx: RuntimeBuildContext):
    from app.services.market.insight_app_service import MarketInsightAppService

    return MarketInsightAppService(
        indicator_service=ctx.require(MARKET_INDICATOR_SERVICE),
        market_query_service=ctx.require(MARKET_QUERY_APP_SERVICE),
        llm_client_factory=_build_llm_client_factory(ctx.require(SYSTEM_LLM_CONFIG_SERVICE)),
    )


def _build_market_websocket_service(_ctx: RuntimeBuildContext):
    from app.services.market.websocket_service import MarketWebSocketService

    return MarketWebSocketService()


def _build_index_data_service(ctx: RuntimeBuildContext):
    from app.services.market.index_data_service import IndexDataService

    return IndexDataService(kline_store=ctx.require(INFRA_KLINE_STORE))


def _build_binance_market_snapshot(ctx: RuntimeBuildContext):
    return ctx.require(MARKET_BINANCE_MARKET_INTEL).snapshot_service


def _build_binance_market_research_store(ctx: RuntimeBuildContext):
    from app.infra.persistence.market.binance_market_research_store import BinanceMarketResearchStore

    return BinanceMarketResearchStore(database_runtime=ctx.require(INFRA_DATABASE_RUNTIME))


def _build_binance_market_intel(ctx: RuntimeBuildContext):
    from app.services.market.binance_market_intel_service import BinanceMarketIntelService

    return BinanceMarketIntelService(
        research_store=ctx.require(MARKET_BINANCE_MARKET_RESEARCH_STORE),
        funding_rate_store=ctx.require(MARKET_FUNDING_RATE_STORE),
        cache_service=ctx.require(INFRA_CACHE_SERVICE),
    )


def _build_binance_web3_client(ctx: RuntimeBuildContext, *, base_url: str, namespace: str, user_agent: str):
    from app.services.market.binance_api_support import BinanceApiSupport
    from config import settings

    return BinanceApiSupport(
        base_url=base_url,
        cache_namespace=namespace,
        user_agent=user_agent,
        cache_service=ctx.require(INFRA_CACHE_SERVICE),
    )


def _build_binance_web3_ranks(ctx: RuntimeBuildContext):
    from app.services.market.binance_web3_rank_gateway import BinanceWeb3RankGateway
    from config import settings

    return BinanceWeb3RankGateway(
        _build_binance_web3_client(
            ctx,
            base_url=settings.BINANCE_WEB3_BASE_URL,
            namespace="binance:web3",
            user_agent="binance-web3/2.1 (Skill)",
        )
    )


def _build_binance_web3_heat_ranks(ctx: RuntimeBuildContext):
    from app.services.market.binance_web3_heat_rank_service import BinanceWeb3HeatRankService

    return BinanceWeb3HeatRankService(ctx.require(MARKET_BINANCE_WEB3_RANKS))


def _build_binance_web3_tokens(ctx: RuntimeBuildContext):
    from app.services.market.binance_web3_tokens import BinanceWeb3TokenService
    from config import settings

    web3_client = _build_binance_web3_client(
        ctx,
        base_url=settings.BINANCE_WEB3_BASE_URL,
        namespace="binance:web3",
        user_agent="binance-web3/2.1 (Skill)",
    )
    kline_client = _build_binance_web3_client(
        ctx,
        base_url="https://dquery.sintral.io",
        namespace="binance:web3:kline",
        user_agent="binance-web3/1.1 (Skill)",
    )
    return BinanceWeb3TokenService(
        web3_client=web3_client,
        kline_client=kline_client,
        kline_store=ctx.require(INFRA_KLINE_STORE),
    )


MARKET_SERVICE_DEFINITIONS: tuple[RuntimeServiceDefinition, ...] = (
    RuntimeServiceDefinition(
        MARKET_MARKET_DATA_SERVICE,
        frozenset({"api"}),
        _build_market_data_service,
        deps=(INFRA_EXCHANGE_GATEWAY, INFRA_KLINE_STORE, INFRA_CACHE_SERVICE),
    ),
    RuntimeServiceDefinition(MARKET_REALTIME_SERVICE, frozenset({"api"}), _build_realtime_service),
    RuntimeServiceDefinition(
        MARKET_INDICATOR_REPOSITORY,
        frozenset({"api", "background"}),
        _build_market_indicator_repository,
        deps=(INFRA_DATABASE_RUNTIME,),
    ),
    RuntimeServiceDefinition(
        MARKET_DLI_CACHE,
        frozenset({"api", "background"}),
        _build_dli_cache,
        deps=(INFRA_CACHE_SERVICE,),
    ),
    RuntimeServiceDefinition(
        MARKET_INDICATOR_SERVICE,
        frozenset({"api"}),
        _build_indicator_service,
        deps=(MARKET_INDICATOR_REPOSITORY, MARKET_DLI_CACHE),
    ),
    RuntimeServiceDefinition(
        MARKET_FUNDING_RATE_STORE,
        frozenset({"api"}),
        _build_funding_rate_store,
        deps=(INFRA_DATABASE_RUNTIME,),
    ),
    RuntimeServiceDefinition(
        MARKET_FUNDING_RATE_SERVICE,
        frozenset({"api"}),
        _build_funding_rate_service,
        deps=(MARKET_FUNDING_RATE_STORE,),
    ),
    RuntimeServiceDefinition(
        MARKET_FUNDING_RATE_APP_SERVICE,
        frozenset({"api"}),
        _build_funding_rate_app_service,
        deps=(MARKET_FUNDING_RATE_SERVICE,),
    ),
    RuntimeServiceDefinition(
        MARKET_BINANCE_MARKET_RESEARCH_STORE,
        frozenset({"api"}),
        _build_binance_market_research_store,
        deps=(INFRA_DATABASE_RUNTIME,),
    ),
    RuntimeServiceDefinition(
        MARKET_QUERY_APP_SERVICE,
        frozenset({"api"}),
        _build_market_query_app_service,
        deps=(MARKET_MARKET_DATA_SERVICE, MARKET_REALTIME_SERVICE, MARKET_BINANCE_MARKET_SNAPSHOT, SYSTEM_LLM_CONFIG_SERVICE),
    ),
    RuntimeServiceDefinition(
        MARKET_INSIGHT_APP_SERVICE,
        frozenset({"api"}),
        _build_market_insight_app_service,
        deps=(MARKET_INDICATOR_SERVICE, MARKET_QUERY_APP_SERVICE, SYSTEM_LLM_CONFIG_SERVICE),
    ),
    RuntimeServiceDefinition(MARKET_WEBSOCKET_SERVICE, frozenset({"api"}), _build_market_websocket_service),
    RuntimeServiceDefinition(
        MARKET_INDEX_DATA_SERVICE,
        frozenset({"api"}),
        _build_index_data_service,
        deps=(INFRA_KLINE_STORE,),
    ),
    RuntimeServiceDefinition(
        MARKET_BINANCE_MARKET_INTEL,
        frozenset({"api"}),
        _build_binance_market_intel,
        deps=(
            INFRA_CACHE_SERVICE,
            MARKET_BINANCE_MARKET_RESEARCH_STORE,
            MARKET_FUNDING_RATE_STORE,
        ),
    ),
    RuntimeServiceDefinition(
        MARKET_BINANCE_MARKET_SNAPSHOT,
        frozenset({"api"}),
        _build_binance_market_snapshot,
        deps=(MARKET_BINANCE_MARKET_INTEL,),
    ),
    RuntimeServiceDefinition(
        MARKET_BINANCE_WEB3_RANKS,
        frozenset({"api"}),
        _build_binance_web3_ranks,
        deps=(INFRA_CACHE_SERVICE,),
    ),
    RuntimeServiceDefinition(
        MARKET_BINANCE_WEB3_HEAT_RANKS,
        frozenset({"api"}),
        _build_binance_web3_heat_ranks,
        deps=(MARKET_BINANCE_WEB3_RANKS,),
    ),
    RuntimeServiceDefinition(
        MARKET_BINANCE_WEB3_TOKENS,
        frozenset({"api"}),
        _build_binance_web3_tokens,
        deps=(INFRA_CACHE_SERVICE, INFRA_KLINE_STORE),
    ),
)
