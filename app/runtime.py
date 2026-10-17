from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from config import settings

if TYPE_CHECKING:
    from app.infra.cache import RedisService
    from app.infra.db.database import DatabaseRuntime
    from app.infra.persistence.market.binance_market_research_store import BinanceMarketResearchStore
    from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
    from app.infra.persistence.market.kline_store import KlineStore
    from app.infra.persistence.sentiment_repository import SentimentRepository
    from app.infra.persistence.runtime_status_repository import RuntimeStatusRepository
    from app.infra.llm_client import LLMClientFactory
    from app.services.currency_service import CurrencyRateService
    from app.services.llm_config_service import LlmConfigService
    from app.services.market.binance_market_intel_service import BinanceMarketIntelService
    from app.services.market.binance_market_snapshot_service import BinanceMarketSnapshotService
    from app.services.market.binance_web3_heat_rank_service import BinanceWeb3HeatRankService
    from app.services.market.binance_web3_rank_gateway import BinanceWeb3RankGateway
    from app.services.market.binance_web3_tokens import BinanceWeb3TokenService
    from app.services.market.exchange_gateway import ExchangeGateway
    from app.services.market.index_data_service import IndexDataService
    from app.services.market.equity_catalog_service import EquityCatalogService
    from app.services.market.indicator_service import IndicatorService
    from app.services.market.insight_app_service import MarketInsightAppService
    from app.services.market.market_data_service import MarketDataService
    from app.services.market.query_app_service import MarketQueryAppService
    from app.services.market.realtime_service import RealtimeService
    from app.services.market.websocket_service import MarketWebSocketService
    from app.services.market_scheduler_runtime import MarketSchedulerRuntime
    from app.services.sentiment_client import SentimentApiClient
    from app.services.sentiment_service import SentimentService
    from app.services.tools.app_service import ToolsAppService
    from app.services.tools.dca_service import DCAService
    from app.services.tools.pair_compare_service import PairCompareService
    from app.services.tools.portfolio_service import PortfolioService
    from app.services.tools.portfolio_analytics_service import PortfolioAnalyticsService
    from app.services.research_service import ResearchService
    from app.services.research_alert_runtime import ResearchAlertRuntime
    from app.services.trade_signal_service import TradeSignalService
    from app.services.trade_signal_evaluation_runtime import TradeSignalEvaluationRuntime
    from app.services.asset_research_service import AssetResearchService
    from app.services.market_screener_service import MarketScreenerService
    from app.services.data_health_service import DataHealthService
    from app.services.research_report_service import ResearchReportService


RuntimeRole = Literal["all", "api", "background"]
RuntimeTarget = Literal["api", "background"]

RUNTIME_ROLE_TARGETS: dict[RuntimeRole, tuple[RuntimeTarget, ...]] = {
    "all": ("api", "background"),
    "api": ("api",),
    "background": ("background",),
}


def runtime_role_targets(role: RuntimeRole) -> tuple[RuntimeTarget, ...]:
    return RUNTIME_ROLE_TARGETS[role]


def runtime_role_has_target(role: RuntimeRole, target: RuntimeTarget) -> bool:
    return target in runtime_role_targets(role)


@dataclass(slots=True)
class InfraRuntimeServices:
    database_runtime: "DatabaseRuntime"
    cache_service: "RedisService"
    runtime_status: "RuntimeStatusRepository | None" = None


@dataclass(slots=True)
class IndicatorRuntimeServices:
    repository: "MarketIndicatorRepository"
    service: "IndicatorService"


@dataclass(slots=True)
class SystemRuntimeServices:
    currency_rates: "CurrencyRateService"
    llm_config: "LlmConfigService"
    llm_clients: "LLMClientFactory | None" = None


@dataclass(slots=True)
class MarketRuntimeServices:
    exchange_gateway: "ExchangeGateway"
    kline_store: "KlineStore"
    data: "MarketDataService"
    realtime: "RealtimeService"
    query: "MarketQueryAppService"
    insight: "MarketInsightAppService"
    websocket: "MarketWebSocketService"
    indexes: "IndexDataService"
    binance_research_store: "BinanceMarketResearchStore"
    binance_intel: "BinanceMarketIntelService"
    binance_snapshot: "BinanceMarketSnapshotService"
    web3_ranks: "BinanceWeb3RankGateway"
    web3_heat_ranks: "BinanceWeb3HeatRankService"
    web3_tokens: "BinanceWeb3TokenService"
    sentiment_client: "SentimentApiClient"
    sentiment_repository: "SentimentRepository"
    sentiment: "SentimentService"
    equity_catalog: "EquityCatalogService | None" = None


@dataclass(slots=True)
class ToolRuntimeServices:
    dca: "DCAService"
    pair_compare: "PairCompareService"
    app: "ToolsAppService"
    portfolios: "PortfolioService"
    portfolio_analytics: "PortfolioAnalyticsService | None" = None


@dataclass(slots=True)
class ApiRuntimeServices:
    system: SystemRuntimeServices
    market: MarketRuntimeServices
    tools: ToolRuntimeServices
    research: "ResearchService | None" = None
    research_alerts: "ResearchAlertRuntime | None" = None
    trade_signals: "TradeSignalService | None" = None
    trade_signal_evaluations: "TradeSignalEvaluationRuntime | None" = None
    asset_research: "AssetResearchService | None" = None
    market_screeners: "MarketScreenerService | None" = None
    data_health: "DataHealthService | None" = None
    research_reports: "ResearchReportService | None" = None


@dataclass(slots=True)
class BackgroundRuntimeServices:
    market_scheduler: "MarketSchedulerRuntime"


@dataclass(slots=True)
class AppRuntimeServices:
    infra: InfraRuntimeServices
    indicators: IndicatorRuntimeServices
    api: ApiRuntimeServices | None = None
    background: BackgroundRuntimeServices | None = None

    def require_api(self) -> ApiRuntimeServices:
        if self.api is None:
            raise RuntimeError("API runtime services are not initialized")
        return self.api

    def require_background(self) -> BackgroundRuntimeServices:
        if self.background is None:
            raise RuntimeError("Background runtime services are not initialized")
        return self.background

    async def start(self) -> None:
        if self.api is not None:
            await self.api.market.binance_intel.start()
            if self.api.research_alerts is not None:
                await self.api.research_alerts.start()
            if self.api.trade_signal_evaluations is not None:
                await self.api.trade_signal_evaluations.start()

    async def shutdown(self) -> None:
        close_actions = []
        if self.api is not None:
            close_actions.append(self.api.market.binance_intel.shutdown())
            if self.api.market.equity_catalog is not None:
                close_actions.append(self.api.market.equity_catalog.aclose())
            if self.api.research_alerts is not None:
                close_actions.append(self.api.research_alerts.shutdown())
            if self.api.trade_signal_evaluations is not None:
                close_actions.append(self.api.trade_signal_evaluations.shutdown())
            if self.api.system.llm_clients is not None:
                close_actions.append(self.api.system.llm_clients.aclose())
            clients = {
                self.api.market.web3_ranks.client,
                self.api.market.web3_tokens.web3_client,
                self.api.market.web3_tokens.kline_client,
            }
            close_actions.extend(client.aclose() for client in clients)
        if close_actions:
            await asyncio.gather(*close_actions, return_exceptions=True)

        try:
            close_cache = getattr(self.infra.cache_service, "aclose", None)
            if close_cache is not None:
                await close_cache()
        finally:
            from app.infra.executor import shutdown_blocking_executors

            await asyncio.to_thread(shutdown_blocking_executors)
            self.infra.database_runtime.dispose()

    def dispose(self) -> None:
        from app.infra.executor import shutdown_blocking_executors

        shutdown_blocking_executors()
        self.infra.database_runtime.dispose()


def build_app_runtime_services(role: RuntimeRole | None = None) -> AppRuntimeServices:
    resolved_role = role or settings.APP_RUNTIME_ROLE

    from app.infra.cache import build_cache_service
    from app.infra.db import build_database_runtime
    from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
    from app.infra.persistence.runtime_status_repository import RuntimeStatusRepository
    from app.services.market.indicator_service import IndicatorService

    database_runtime = build_database_runtime(settings)
    cache_service = build_cache_service(settings)
    indicator_repository = MarketIndicatorRepository(database_runtime=database_runtime)
    indicator_service = IndicatorService(repository=indicator_repository)
    runtime_status = RuntimeStatusRepository(database_runtime)
    infra = InfraRuntimeServices(
        database_runtime=database_runtime,
        cache_service=cache_service,
        runtime_status=runtime_status,
    )
    indicators = IndicatorRuntimeServices(
        repository=indicator_repository,
        service=indicator_service,
    )
    api_runtime: ApiRuntimeServices | None = None
    background_runtime: BackgroundRuntimeServices | None = None

    if runtime_role_has_target(resolved_role, "api"):
        from app.infra.persistence.market.binance_market_research_store import BinanceMarketResearchStore
        from app.infra.persistence.market.kline_store import KlineStore
        from app.infra.persistence.sentiment_repository import SentimentRepository
        from app.infra.persistence.portfolio_repository import PortfolioRepository
        from app.infra.persistence.research_repository import ResearchRepository
        from app.infra.persistence.trade_signal_repository import TradeSignalRepository
        from app.infra.persistence.market_screener_repository import MarketScreenerRepository
        from app.infra.persistence.data_health_repository import DataHealthRepository
        from app.infra.persistence.research_report_repository import ResearchReportRepository
        from app.infra.db.schema_runtime import verify_database_schema
        from app.infra.llm_client import LLMClientFactory
        from app.services.currency_service import CurrencyRateService
        from app.services.llm_config_service import LlmConfigService
        from app.services.market.binance_api_support import BinanceApiSupport
        from app.services.market.binance_market_intel_service import BinanceMarketIntelService
        from app.services.market.binance_web3_heat_rank_service import BinanceWeb3HeatRankService
        from app.services.market.binance_web3_rank_gateway import BinanceWeb3RankGateway
        from app.services.market.binance_web3_tokens import BinanceWeb3TokenService
        from app.services.market.exchange_gateway import ExchangeGateway
        from app.services.market.index_data_service import IndexDataService
        from app.services.market.equity_catalog_service import EquityCatalogService
        from app.services.market.insight_app_service import MarketInsightAppService
        from app.services.market.market_data_service import MarketDataService
        from app.services.market.query_app_service import MarketQueryAppService
        from app.services.market.realtime_service import RealtimeService
        from app.services.market.websocket_service import MarketWebSocketService
        from app.services.sentiment_client import SentimentApiClient
        from app.services.sentiment_service import SentimentService
        from app.services.tools.app_service import ToolsAppService
        from app.services.tools.dca_service import DCAService
        from app.services.tools.pair_compare_service import PairCompareService
        from app.services.tools.portfolio_service import PortfolioService
        from app.services.tools.portfolio_analytics_service import PortfolioAnalyticsService
        from app.services.research_service import ResearchService
        from app.services.research_alert_runtime import ResearchAlertRuntime
        from app.services.trade_signal_service import TradeSignalService
        from app.services.trade_signal_evaluation_runtime import TradeSignalEvaluationRuntime
        from app.services.asset_research_service import AssetResearchService
        from app.services.market_screener_service import MarketScreenerService
        from app.services.data_health_service import DataHealthService
        from app.services.research_report_service import ResearchReportService

        exchange_gateway = ExchangeGateway(exchange_id=settings.EXCHANGE_ID)
        kline_store = KlineStore(database_runtime=database_runtime)
        market_data = MarketDataService(
            exchange_gateway=exchange_gateway,
            kline_store=kline_store,
            cache_service=cache_service,
        )
        realtime = RealtimeService()
        currency_rates = CurrencyRateService()
        llm_config = LlmConfigService()
        llm_clients = LLMClientFactory(llm_config)
        binance_research_store = BinanceMarketResearchStore(database_runtime=database_runtime)
        binance_intel = BinanceMarketIntelService(
            research_store=binance_research_store,
            cache_service=cache_service,
        )
        binance_snapshot = binance_intel.snapshot_service
        market_query = MarketQueryAppService(
            market_data_service=market_data,
            realtime_service=realtime,
            binance_snapshot_service=binance_snapshot,
            llm_client_factory=llm_clients,
        )
        trade_signal_repository = TradeSignalRepository(database_runtime)
        market_insight = MarketInsightAppService(indicator_service=indicator_service)
        market_websocket = MarketWebSocketService()
        index_data = IndexDataService(kline_store=kline_store)
        web3_client = BinanceApiSupport(
            base_url=settings.BINANCE_WEB3_BASE_URL,
            cache_namespace="binance:web3",
            user_agent="heimdall/web3",
            cache_service=cache_service,
        )
        web3_ranks = BinanceWeb3RankGateway(web3_client)
        web3_heat_ranks = BinanceWeb3HeatRankService(web3_ranks)
        web3_tokens = BinanceWeb3TokenService(
            web3_client=web3_client,
            kline_client=BinanceApiSupport(
                base_url=settings.BINANCE_WEB3_KLINE_BASE_URL,
                cache_namespace="binance:web3:kline",
                user_agent="heimdall/web3-kline",
                cache_service=cache_service,
            ),
            kline_store=kline_store,
        )
        sentiment_client = SentimentApiClient(settings.SENTIMENT_API_URL)
        sentiment_repository = SentimentRepository(database_runtime=database_runtime)
        sentiment = SentimentService(
            client=sentiment_client,
            repository=sentiment_repository,
        )
        dca = DCAService(
            market_data_service=market_data,
            sentiment_service=sentiment,
            index_data_service=index_data,
        )
        pair_compare = PairCompareService(
            market_data_service=market_data,
            index_data_service=index_data,
        )
        tools_app = ToolsAppService(
            dca_service=dca,
            pair_compare_service=pair_compare,
            cache_service=cache_service,
        )
        portfolio_repository = PortfolioRepository(database_runtime)
        research_repository = ResearchRepository(database_runtime)
        portfolio_service = PortfolioService(portfolio_repository)
        portfolio_analytics_service = PortfolioAnalyticsService(
            portfolio_service=portfolio_service,
            market_query_service=market_query,
            index_data_service=index_data,
        )
        research_service = ResearchService(research_repository)
        research_alert_runtime = ResearchAlertRuntime(
            research_repository=research_repository,
            market_query_service=market_query,
            binance_market_service=binance_intel,
            portfolio_repository=portfolio_repository,
        )
        trade_signal_service = TradeSignalService(trade_signal_repository)
        trade_signal_evaluation_runtime = TradeSignalEvaluationRuntime(
            repository=trade_signal_repository,
            market_query_service=market_query,
        )
        asset_research_service = AssetResearchService(
            research_repository=research_repository,
            signal_repository=trade_signal_repository,
            market_query_service=market_query,
            index_data_service=index_data,
            binance_market_service=binance_intel,
            binance_web3_heat_rank_service=web3_heat_ranks,
            binance_web3_token_service=web3_tokens,
            pair_compare_service=pair_compare,
        )
        market_screener_service = MarketScreenerService(
            repository=MarketScreenerRepository(database_runtime),
            binance_market_service=binance_intel,
            market_query_service=market_query,
            binance_web3_heat_rank_service=web3_heat_ranks,
        )
        data_health_service = DataHealthService(
            repository=DataHealthRepository(database_runtime),
            database_verifier=lambda: verify_database_schema(database_runtime),
            market_query_service=market_query,
            index_data_service=index_data,
            binance_market_service=binance_intel,
            research_alert_runtime=research_alert_runtime,
            trade_signal_runtime=trade_signal_evaluation_runtime,
            cache_service=cache_service,
        )
        research_report_service = ResearchReportService(
            repository=ResearchReportRepository(database_runtime),
            research_repository=research_repository,
            signal_repository=trade_signal_repository,
            portfolio_service=portfolio_service,
            data_health_service=data_health_service,
            asset_research_service=asset_research_service,
            portfolio_analytics_service=portfolio_analytics_service,
        )
        api_runtime = ApiRuntimeServices(
            system=SystemRuntimeServices(
                currency_rates=currency_rates,
                llm_config=llm_config,
                llm_clients=llm_clients,
            ),
            market=MarketRuntimeServices(
                exchange_gateway=exchange_gateway,
                kline_store=kline_store,
                data=market_data,
                realtime=realtime,
                query=market_query,
                insight=market_insight,
                websocket=market_websocket,
                indexes=index_data,
                binance_research_store=binance_research_store,
                binance_intel=binance_intel,
                binance_snapshot=binance_snapshot,
                web3_ranks=web3_ranks,
                web3_heat_ranks=web3_heat_ranks,
                web3_tokens=web3_tokens,
                sentiment_client=sentiment_client,
                sentiment_repository=sentiment_repository,
                sentiment=sentiment,
                equity_catalog=EquityCatalogService(cache_service=cache_service),
            ),
            tools=ToolRuntimeServices(
                dca=dca,
                pair_compare=pair_compare,
                app=tools_app,
                portfolios=portfolio_service,
                portfolio_analytics=portfolio_analytics_service,
            ),
            research=research_service,
            research_alerts=research_alert_runtime,
            trade_signals=trade_signal_service,
            trade_signal_evaluations=trade_signal_evaluation_runtime,
            asset_research=asset_research_service,
            market_screeners=market_screener_service,
            data_health=data_health_service,
            research_reports=research_report_service,
        )

    if runtime_role_has_target(resolved_role, "background"):
        from app.infra.persistence.data_retention import cleanup_old_data
        from app.services.market_scheduler_runtime import MarketSchedulerRuntime

        background_runtime = BackgroundRuntimeServices(
            market_scheduler=MarketSchedulerRuntime(
                indicator_repository=indicator_repository,
                cleanup_old_data=lambda: cleanup_old_data(database_runtime),
                runtime_status_repository=runtime_status,
            )
        )

    return AppRuntimeServices(
        infra=infra,
        indicators=indicators,
        api=api_runtime,
        background=background_runtime,
    )
