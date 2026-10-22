"""
Shared pytest fixtures for OpenTrading tests.
"""
from contextlib import asynccontextmanager
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app.runtime import (
    ApiRuntimeServices,
    AppRuntimeServices,
    IndicatorRuntimeServices,
    InfraRuntimeServices,
    MarketRuntimeServices,
    SystemRuntimeServices,
    ToolRuntimeServices,
)
from app.infra.db import build_database_runtime
from app.infra.db.schema_runtime import prepare_db
from config.settings import AppSettings
from test.regression_support import (
    StubBinanceMarketService,
    StubBinanceWeb3HeatRanksService,
    StubBinanceWeb3RanksService,
    StubBinanceWeb3TokensService,
    StubMarketInsightAppService,
    StubMarketQueryAppService,
    StubToolsAppService,
)


class StubCurrencyRateService:
    async def get_rates(self):
        return {
            "base": "USD",
            "rates": {"USD": 1.0, "CNY": 7.2},
            "supported": [
                {"code": "USD", "name": "US Dollar", "symbol": "$", "locale": "en-US", "fraction_digits": 2},
                {"code": "CNY", "name": "人民币", "symbol": "¥", "locale": "zh-CN", "fraction_digits": 2},
            ],
            "updated_at": "2026-04-14T00:00:00+00:00",
            "source": "test",
            "is_fallback": False,
        }


class StubLlmConfigService:
    def read_config(self):
        return {
            "provider": "deepseek",
            "apiKey": "",
            "apiKeySet": False,
            "apiKeyPreview": "",
            "baseUrl": "https://api.deepseek.com/v1",
            "modelId": "deepseek-chat",
            "reasoningEnabled": False,
            "presets": [
                {
                    "id": "deepseek",
                    "label": "DeepSeek",
                    "baseUrl": "https://api.deepseek.com/v1",
                    "defaultModel": "deepseek-chat",
                    "supportsReasoning": True,
                }
            ],
        }

    def save_config(self, payload):
        return self.read_config()


@pytest.fixture(autouse=True)
def installed_database_runtime(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    runtime = build_database_runtime(AppSettings(DATABASE_URL=database_url))
    prepare_db(runtime)
    try:
        yield runtime
    finally:
        runtime.dispose()


@pytest.fixture
def db_engine(installed_database_runtime):
    """Expose the installed runtime engine to tests that need direct SQLAlchemy access."""
    return installed_database_runtime.engine


@pytest.fixture
def db_session(db_engine):
    """Provide a transactional database session that rolls back after each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def mock_kline_data():
    """Sample OHLCV data for testing: [timestamp_ms, open, high, low, close, volume]."""
    base_ts = 1700000000000  # Nov 2023
    return [
        [base_ts + i * 3600000, 40000 + i * 10, 40050 + i * 10, 39950 + i * 10, 40000 + i * 15, 100 + i]
        for i in range(300)
    ]


@pytest.fixture
def api_harness(installed_database_runtime):
    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    services = {
        "market_query_app": StubMarketQueryAppService(),
        "market_insight_app": StubMarketInsightAppService(),
        "binance_market_service": StubBinanceMarketService(),
        "binance_web3_ranks": StubBinanceWeb3RanksService(),
        "binance_web3_heat_ranks": StubBinanceWeb3HeatRanksService(),
        "binance_web3_tokens": StubBinanceWeb3TokensService(),
        "tools_app": StubToolsAppService(),
        "currency_rate": StubCurrencyRateService(),
        "llm_config": StubLlmConfigService(),
    }
    app = main_module.app
    app.state.runtime_services = AppRuntimeServices(
        infra=InfraRuntimeServices(installed_database_runtime, object()),
        indicators=IndicatorRuntimeServices(object(), object()),
        api=ApiRuntimeServices(
            system=SystemRuntimeServices(
                services["currency_rate"],
                services["llm_config"],
            ),
            market=MarketRuntimeServices(
                exchange_gateway=object(),
                kline_store=object(),
                data=object(),
                realtime=object(),
                query=services["market_query_app"],
                insight=services["market_insight_app"],
                websocket=object(),
                indexes=object(),
                binance_research_store=object(),
                binance_intel=services["binance_market_service"],
                binance_snapshot=object(),
                web3_ranks=services["binance_web3_ranks"],
                web3_heat_ranks=services["binance_web3_heat_ranks"],
                web3_tokens=services["binance_web3_tokens"],
                sentiment_client=object(),
                sentiment_repository=object(),
                sentiment=object(),
            ),
            tools=ToolRuntimeServices(object(), object(), services["tools_app"], object()),
        ),
    )
    app.state.database_error = None
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides = {}

    with TestClient(app) as client:
        yield {"client": client, **services}

    app.dependency_overrides.clear()
    app.router.lifespan_context = original_lifespan
