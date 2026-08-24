from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.domain.market.dli_catalog import DLI_SCORING_DEFINITIONS, market_indicator_meta_catalog
from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
from app.services.market.dli_cache import DliLiquidityCache
from app.services.market.dli_scoring import DliScoreEngine
from app.services.market.dli_service import DliLiquidityService
from app.services.market.indicator_service import IndicatorService


def test_dli_liquidity_service_builds_weighted_pressure_score(installed_database_runtime):
    repository = MarketIndicatorRepository(database_runtime=installed_database_runtime)
    now = datetime.now().replace(microsecond=0)
    points = []
    for definition in DLI_SCORING_DEFINITIONS:
        for index in range(90):
            timestamp = now - timedelta(days=89 - index)
            value = 100.0 + index if definition.polarity == "lower_tightens" else 200.0 - index
            points.append({"indicator_id": definition.id, "timestamp": timestamp, "value": value})
    repository.upsert_points(points, market_indicator_meta_catalog())

    payload = DliLiquidityService(repository).build(days=90).model_dump()

    assert payload["score"] is not None
    assert payload["score"] < 20
    assert payload["score_percentile"] is not None
    assert 0 <= payload["score_percentile"] <= 100
    assert payload["state"] in {"中性偏松", "流动性宽松"}
    assert payload["coverage"] == 100.0
    assert {"p20", "p50", "p80"} <= set(payload["thresholds"])
    assert payload["thresholds"]["sample_size"] > 0
    assert sum(item["effective_weight"] for item in payload["components"]) == pytest.approx(100.0, abs=0.001)
    assert {item["indicator_id"] for item in payload["components"]} == {item.id for item in DLI_SCORING_DEFINITIONS}
    assert payload["alerts"]
    assert any(alert.startswith("美联储资产负债表当前") for alert in payload["alerts"])


def test_dli_liquidity_service_reports_missing_coverage(installed_database_runtime):
    repository = MarketIndicatorRepository(database_runtime=installed_database_runtime)
    now = datetime.now().replace(microsecond=0)
    points = [
        {"indicator_id": "FED_BALANCE", "timestamp": now - timedelta(days=2), "value": 100.0},
        {"indicator_id": "FED_BALANCE", "timestamp": now - timedelta(days=1), "value": 101.0},
        {"indicator_id": "FED_BALANCE", "timestamp": now, "value": 102.0},
    ]
    repository.upsert_points(points, market_indicator_meta_catalog())

    payload = DliLiquidityService(repository).build(days=30).model_dump()

    assert payload["score"] is not None
    assert round(payload["coverage"], 2) == round(65.0 / 3.0, 2)
    missing = [item for item in payload["components"] if item["score"] is None]
    assert missing
    assert all(item["missing_reason"] for item in missing)


def test_dli_liquidity_state_uses_four_regimes():
    assert DliScoreEngine.state(19.0, 20.0, 50.0, 80.0) == ("流动性宽松", "support")
    assert DliScoreEngine.state(32.0, 20.0, 50.0, 80.0) == ("中性偏松", "support")
    assert DliScoreEngine.state(51.0, 20.0, 50.0, 80.0) == ("中性偏紧", "pressure")
    assert DliScoreEngine.state(81.0, 20.0, 50.0, 80.0) == ("流动性收紧", "pressure")


def test_dli_liquidity_score_percentile_uses_history_distribution():
    assert DliScoreEngine.score_percentile(32.0, [10.0, 30.0, 40.0, 90.0]) == 50.0


class CountingIndicatorRepository:
    def __init__(self) -> None:
        self.history_reads = 0

    def get_history_points(self, indicator_ids, *, start_date=None):
        self.history_reads += 1
        return {}

    def list_active_meta(self, category=None):
        return []


def test_indicator_service_caches_dli_payload_until_invalidated():
    repository = CountingIndicatorRepository()
    cache = DliLiquidityCache(ttl_seconds=60)
    service = IndicatorService(repository, dli_cache=cache)

    first = service.get_dli_liquidity(days=30)
    second = service.get_dli_liquidity(days=30)

    assert first == second
    assert repository.history_reads == 1

    cache.invalidate_all()
    service.get_dli_liquidity(days=30)

    assert repository.history_reads == 2


class StaticIndicatorRepository:
    def list_active_meta(self, category=None):
        return [
            {"id": "HASHRATE", "name": "BTC Hashrate", "category": "Onchain", "unit": "EH/s"},
            {"id": "DIFFICULTY", "name": "Mining Difficulty", "category": "Onchain", "unit": "T"},
            {"id": "STABLECOIN_CAP", "name": "Stablecoin Market Cap", "category": "Onchain", "unit": "USD"},
        ]

    def get_history_points(self, indicator_ids, *, start_date=None):
        now = datetime.now().replace(microsecond=0)
        return {
            "HASHRATE": [{"date": now.isoformat(), "value": 1_008_000_000_000_000_000_000.0}],
            "DIFFICULTY": [{"date": now.isoformat(), "value": 132_470_000_000_000.0}],
            "STABLECOIN_CAP": [{"date": now.isoformat(), "value": 320_850_000_000.0}],
        }


def test_indicator_service_returns_display_unit_values_for_market_indicator_api():
    payload = IndicatorService(StaticIndicatorRepository()).get_indicators(category="Onchain", days=30)
    values = {item.indicator_id: item.current_value for item in payload}

    assert values["HASHRATE"] == pytest.approx(1008.0)
    assert values["DIFFICULTY"] == pytest.approx(132.47)
    assert values["STABLECOIN_CAP"] == pytest.approx(320_850_000_000.0)
