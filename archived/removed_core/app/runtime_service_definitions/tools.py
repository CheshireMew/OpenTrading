from __future__ import annotations

from app.runtime_definition import RuntimeBuildContext, RuntimeServiceDefinition
from app.runtime_refs import (
    INFRA_CACHE_SERVICE,
    INFRA_DATABASE_RUNTIME,
    MARKET_INDEX_DATA_SERVICE,
    MARKET_MARKET_DATA_SERVICE,
    TOOLS_DCA_SERVICE,
    TOOLS_PAIR_COMPARE_SERVICE,
    TOOLS_SENTIMENT_API_CLIENT,
    TOOLS_SENTIMENT_REPOSITORY,
    TOOLS_SENTIMENT_SERVICE,
    TOOLS_TOOLS_APP_SERVICE,
)
from config import settings


def _build_sentiment_api_client(_ctx: RuntimeBuildContext):
    from app.services.sentiment_client import SentimentApiClient

    return SentimentApiClient(settings.SENTIMENT_API_URL)


def _build_sentiment_repository(ctx: RuntimeBuildContext):
    from app.infra.persistence.sentiment_repository import SentimentRepository

    return SentimentRepository(database_runtime=ctx.require(INFRA_DATABASE_RUNTIME))


def _build_sentiment_service(ctx: RuntimeBuildContext):
    from app.services.sentiment_service import SentimentService

    return SentimentService(
        client=ctx.require(TOOLS_SENTIMENT_API_CLIENT),
        repository=ctx.require(TOOLS_SENTIMENT_REPOSITORY),
    )


def _build_dca_service(ctx: RuntimeBuildContext):
    from app.services.tools.dca_service import DCAService

    return DCAService(
        market_data_service=ctx.require(MARKET_MARKET_DATA_SERVICE),
        sentiment_service=ctx.require(TOOLS_SENTIMENT_SERVICE),
        index_data_service=ctx.require(MARKET_INDEX_DATA_SERVICE),
    )


def _build_pair_compare_service(ctx: RuntimeBuildContext):
    from app.services.tools.pair_compare_service import PairCompareService

    return PairCompareService(
        market_data_service=ctx.require(MARKET_MARKET_DATA_SERVICE),
        index_data_service=ctx.require(MARKET_INDEX_DATA_SERVICE),
    )


def _build_tools_app_service(ctx: RuntimeBuildContext):
    from app.services.tools.app_service import ToolsAppService

    return ToolsAppService(
        dca_service=ctx.require(TOOLS_DCA_SERVICE),
        pair_compare_service=ctx.require(TOOLS_PAIR_COMPARE_SERVICE),
        cache_service=ctx.require(INFRA_CACHE_SERVICE),
    )


TOOL_SERVICE_DEFINITIONS: tuple[RuntimeServiceDefinition, ...] = (
    RuntimeServiceDefinition(TOOLS_SENTIMENT_API_CLIENT, frozenset({"api"}), _build_sentiment_api_client),
    RuntimeServiceDefinition(
        TOOLS_SENTIMENT_REPOSITORY,
        frozenset({"api"}),
        _build_sentiment_repository,
        deps=(INFRA_DATABASE_RUNTIME,),
    ),
    RuntimeServiceDefinition(
        TOOLS_SENTIMENT_SERVICE,
        frozenset({"api"}),
        _build_sentiment_service,
        deps=(TOOLS_SENTIMENT_API_CLIENT, TOOLS_SENTIMENT_REPOSITORY),
    ),
    RuntimeServiceDefinition(
        TOOLS_DCA_SERVICE,
        frozenset({"api"}),
        _build_dca_service,
        deps=(MARKET_MARKET_DATA_SERVICE, TOOLS_SENTIMENT_SERVICE, MARKET_INDEX_DATA_SERVICE),
    ),
    RuntimeServiceDefinition(
        TOOLS_PAIR_COMPARE_SERVICE,
        frozenset({"api"}),
        _build_pair_compare_service,
        deps=(MARKET_MARKET_DATA_SERVICE, MARKET_INDEX_DATA_SERVICE),
    ),
    RuntimeServiceDefinition(
        TOOLS_TOOLS_APP_SERVICE,
        frozenset({"api"}),
        _build_tools_app_service,
        deps=(TOOLS_DCA_SERVICE, TOOLS_PAIR_COMPARE_SERVICE, INFRA_CACHE_SERVICE),
    ),
)
