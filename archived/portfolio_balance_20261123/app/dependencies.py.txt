from __future__ import annotations

from typing import TYPE_CHECKING, cast

from starlette.requests import HTTPConnection

from app.runtime import AppRuntimeServices

if TYPE_CHECKING:
    from app.infra.db.database import DatabaseRuntime
    from app.services.currency_service import CurrencyRateService
    from app.services.llm_config_service import LlmConfigService
    from app.services.market.binance_market_intel_service import BinanceMarketIntelService
    from app.services.market.binance_web3_heat_rank_service import BinanceWeb3HeatRankService
    from app.services.market.binance_web3_rank_gateway import BinanceWeb3RankGateway
    from app.services.market.binance_web3_tokens import BinanceWeb3TokenService
    from app.services.market.index_data_service import IndexDataService
    from app.services.market.equity_catalog_service import EquityCatalogService
    from app.services.market.insight_app_service import MarketInsightAppService
    from app.services.market.query_app_service import MarketQueryAppService
    from app.services.market.websocket_service import MarketWebSocketService
    from app.services.tools.app_service import ToolsAppService
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


def get_runtime_services(connection: HTTPConnection) -> AppRuntimeServices:
    runtime_services = getattr(connection.app.state, "runtime_services", None)
    if runtime_services is None:
        raise RuntimeError("App runtime services are not initialized")
    return cast(AppRuntimeServices, runtime_services)


def get_database_runtime(connection: HTTPConnection) -> "DatabaseRuntime":
    return get_runtime_services(connection).infra.database_runtime


def get_currency_rate_service(connection: HTTPConnection) -> "CurrencyRateService":
    return get_runtime_services(connection).require_api().system.currency_rates


def get_llm_config_service(connection: HTTPConnection) -> "LlmConfigService":
    return get_runtime_services(connection).require_api().system.llm_config


def get_tools_app_service(connection: HTTPConnection) -> "ToolsAppService":
    return get_runtime_services(connection).require_api().tools.app


def get_portfolio_service(connection: HTTPConnection) -> "PortfolioService":
    return get_runtime_services(connection).require_api().tools.portfolios


def get_portfolio_analytics_service(connection: HTTPConnection) -> "PortfolioAnalyticsService":
    service = get_runtime_services(connection).require_api().tools.portfolio_analytics
    if service is None:
        raise RuntimeError("Portfolio analytics service is not initialized")
    return service


def get_research_service(connection: HTTPConnection) -> "ResearchService":
    service = get_runtime_services(connection).require_api().research
    if service is None:
        raise RuntimeError("Research service is not initialized")
    return service


def get_research_alert_runtime(connection: HTTPConnection) -> "ResearchAlertRuntime":
    service = get_runtime_services(connection).require_api().research_alerts
    if service is None:
        raise RuntimeError("Research alert runtime is not initialized")
    return service


def get_trade_signal_service(connection: HTTPConnection) -> "TradeSignalService":
    service = get_runtime_services(connection).require_api().trade_signals
    if service is None:
        raise RuntimeError("Trade signal service is not initialized")
    return service


def get_trade_signal_evaluation_runtime(connection: HTTPConnection) -> "TradeSignalEvaluationRuntime":
    service = get_runtime_services(connection).require_api().trade_signal_evaluations
    if service is None:
        raise RuntimeError("Trade signal evaluation runtime is not initialized")
    return service


def get_asset_research_service(connection: HTTPConnection) -> "AssetResearchService":
    service = get_runtime_services(connection).require_api().asset_research
    if service is None:
        raise RuntimeError("Asset research service is not initialized")
    return service


def get_market_screener_service(connection: HTTPConnection) -> "MarketScreenerService":
    service = get_runtime_services(connection).require_api().market_screeners
    if service is None:
        raise RuntimeError("Market screener service is not initialized")
    return service


def get_data_health_service(connection: HTTPConnection) -> "DataHealthService":
    service = get_runtime_services(connection).require_api().data_health
    if service is None:
        raise RuntimeError("Data health service is not initialized")
    return service


def get_research_report_service(connection: HTTPConnection) -> "ResearchReportService":
    service = get_runtime_services(connection).require_api().research_reports
    if service is None:
        raise RuntimeError("Research report service is not initialized")
    return service


def get_market_query_service(connection: HTTPConnection) -> "MarketQueryAppService":
    return get_runtime_services(connection).require_api().market.query


def get_market_insight_service(connection: HTTPConnection) -> "MarketInsightAppService":
    return get_runtime_services(connection).require_api().market.insight


def get_market_websocket_service(connection: HTTPConnection) -> "MarketWebSocketService":
    return get_runtime_services(connection).require_api().market.websocket


def get_index_data_service(connection: HTTPConnection) -> "IndexDataService":
    return get_runtime_services(connection).require_api().market.indexes


def get_equity_catalog_service(connection: HTTPConnection) -> "EquityCatalogService":
    service = get_runtime_services(connection).require_api().market.equity_catalog
    if service is None:
        raise RuntimeError("Equity catalog service is not initialized")
    return service


def get_binance_market_intel_service(connection: HTTPConnection) -> "BinanceMarketIntelService":
    return get_runtime_services(connection).require_api().market.binance_intel


def get_binance_web3_rank_gateway(connection: HTTPConnection) -> "BinanceWeb3RankGateway":
    return get_runtime_services(connection).require_api().market.web3_ranks


def get_binance_web3_heat_rank_service(connection: HTTPConnection) -> "BinanceWeb3HeatRankService":
    return get_runtime_services(connection).require_api().market.web3_heat_ranks


def get_binance_web3_token_service(connection: HTTPConnection) -> "BinanceWeb3TokenService":
    return get_runtime_services(connection).require_api().market.web3_tokens
