from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


TService = TypeVar("TService")


@dataclass(frozen=True, slots=True)
class RuntimeServiceRef(Generic[TService]):
    section: str
    name: str

    @property
    def key(self) -> str:
        return f"{self.section}.{self.name}"


INFRA_EXCHANGE_GATEWAY = RuntimeServiceRef("infra", "exchange_gateway")
INFRA_DATABASE_RUNTIME = RuntimeServiceRef("infra", "database_runtime")
INFRA_KLINE_STORE = RuntimeServiceRef("infra", "kline_store")
INFRA_CACHE_SERVICE = RuntimeServiceRef("infra", "cache_service")

MARKET_MARKET_DATA_SERVICE = RuntimeServiceRef("market", "market_data_service")
MARKET_REALTIME_SERVICE = RuntimeServiceRef("market", "realtime_service")
MARKET_INDICATOR_REPOSITORY = RuntimeServiceRef("market", "market_indicator_repository")
MARKET_DLI_CACHE = RuntimeServiceRef("market", "dli_cache")
MARKET_INDICATOR_SERVICE = RuntimeServiceRef("market", "indicator_service")
MARKET_FUNDING_RATE_STORE = RuntimeServiceRef("market", "funding_rate_store")
MARKET_FUNDING_RATE_SERVICE = RuntimeServiceRef("market", "funding_rate_service")
MARKET_FUNDING_RATE_APP_SERVICE = RuntimeServiceRef("market", "funding_rate_app_service")
MARKET_QUERY_APP_SERVICE = RuntimeServiceRef("market", "market_query_app_service")
MARKET_INSIGHT_APP_SERVICE = RuntimeServiceRef("market", "market_insight_app_service")
MARKET_WEBSOCKET_SERVICE = RuntimeServiceRef("market", "market_websocket_service")
MARKET_INDEX_DATA_SERVICE = RuntimeServiceRef("market", "index_data_service")
MARKET_BINANCE_MARKET_SNAPSHOT = RuntimeServiceRef("market", "binance_market_snapshot")
MARKET_BINANCE_MARKET_RESEARCH_STORE = RuntimeServiceRef("market", "binance_market_research_store")
MARKET_BINANCE_MARKET_INTEL = RuntimeServiceRef("market", "binance_market_intel")
MARKET_BINANCE_WEB3_RANKS = RuntimeServiceRef("market", "binance_web3_ranks")
MARKET_BINANCE_WEB3_HEAT_RANKS = RuntimeServiceRef("market", "binance_web3_heat_ranks")
MARKET_BINANCE_WEB3_TOKENS = RuntimeServiceRef("market", "binance_web3_tokens")

TOOLS_SENTIMENT_API_CLIENT = RuntimeServiceRef("tools", "sentiment_api_client")
TOOLS_SENTIMENT_REPOSITORY = RuntimeServiceRef("tools", "sentiment_repository")
TOOLS_SENTIMENT_SERVICE = RuntimeServiceRef("tools", "sentiment_service")
TOOLS_DCA_SERVICE = RuntimeServiceRef("tools", "dca_service")
TOOLS_PAIR_COMPARE_SERVICE = RuntimeServiceRef("tools", "pair_compare_service")
TOOLS_TOOLS_APP_SERVICE = RuntimeServiceRef("tools", "tools_app_service")

SYSTEM_CURRENCY_RATE_SERVICE = RuntimeServiceRef("system", "currency_rate_service")
SYSTEM_LLM_CONFIG_SERVICE = RuntimeServiceRef("system", "llm_config_service")
SYSTEM_FRED_API_CONFIG_SERVICE = RuntimeServiceRef("system", "fred_api_config_service")
SYSTEM_MARKET_SCHEDULER_RUNTIME = RuntimeServiceRef("system", "market_scheduler_runtime")
