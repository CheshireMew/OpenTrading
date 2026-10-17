from datetime import datetime, timedelta

from app.domain.market.indicator_catalog import MARKET_INDICATOR_META
from app.infra.persistence.data_health_repository import DataHealthRepository
from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
from app.services.data_health_service import DataHealthService
from app.services.market.indicator_service import IndicatorService
from app.services.market_scheduler_runtime import _build_indicator_providers
from config.settings import AppSettings


def test_retired_macro_history_is_preserved_but_not_served_or_monitored(installed_database_runtime):
    repository = MarketIndicatorRepository(database_runtime=installed_database_runtime)
    now = datetime.now()
    retired = {"US10Y", "US02Y", "FED_RATE", "NASDAQ", "WTI", "GOLD"}
    repository.upsert_points([
        {"indicator_id": indicator_id, "timestamp": now - timedelta(days=300), "value": 1.0}
        for indicator_id in retired
    ], {indicator_id: (indicator_id, "Macro", "%") for indicator_id in retired})
    repository.upsert_points([
        {"indicator_id": "FEAR_GREED", "timestamp": now, "value": 55.0},
    ], MARKET_INDICATOR_META)

    service = IndicatorService(repository)
    assert [item.indicator_id for item in service.get_indicators(None, 365)] == ["FEAR_GREED"]
    assert service.get_indicators("Macro", 365) == []
    assert len(repository.get_history_points(list(retired))) == len(retired)

    snapshot = DataHealthRepository(installed_database_runtime).snapshot()
    assert [row["indicatorId"] for row in snapshot["indicators"]] == ["FEAR_GREED"]
    health = DataHealthService._indicator_source(snapshot, now)
    assert health.status == "ready"
    assert health.recordCount == 1


def test_background_collection_only_builds_current_signal_providers():
    assert {type(provider).__name__ for provider in _build_indicator_providers()} == {
        "OnchainProvider", "SentimentProvider", "TechCalculatorProvider",
    }
    assert not any(name.startswith("FRED_") for name in AppSettings.model_fields)


def test_retired_fred_configuration_routes_are_unavailable(api_harness):
    client = api_harness["client"]
    assert client.get("/api/v1/fred-api-config").status_code == 404
    # The application's SPA fallback rejects PUT with 405 when no API route matches.
    assert client.put("/api/v1/fred-api-config", json={"apiKey": "unused"}).status_code in {404, 405}
    assert "/api/v1/fred-api-config" not in client.get("/openapi.json").json()["paths"]
