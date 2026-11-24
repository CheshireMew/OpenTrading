from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.contracts.data_health import DataRepairCommand
from app.infra.persistence.data_health_repository import DataHealthRepository
from app.infra.persistence.market.kline_store import KlineStore
from app.services.data_health_service import DataHealthService


class StubSnapshot:
    def health_snapshot(self):
        return {"status": "ready", "seedSuccessCount": 3, "activeStreams": 3, "error": None}

    async def get_market_page_snapshot_data(self):
        return {
            "updated_at": int(datetime.now(timezone.utc).timestamp() * 1000),
            "spot_ticker": {"items": [{}]},
            "usdm_ticker": {"items": [{}]},
            "usdm_mark": {"items": [{}]},
        }


def test_explicit_memory_cache_health_does_not_report_a_redis_failure():
    service = DataHealthService(
        repository=None, database_verifier=None, market_query_service=None,
        index_data_service=None, binance_market_service=None,
        research_alert_runtime=None, trade_signal_runtime=None,
        cache_service=SimpleNamespace(runtime_backend="memory", local_entry_count=2, local_byte_size=128),
    )
    result = service._cache_source()
    assert result.status == "ready"
    assert result.detail == "本地内存缓存可用"
    assert result.metadata["backend"] == "memory"


@pytest.mark.asyncio
async def test_data_health_reports_coverage_and_scoped_database_repair(installed_database_runtime):
    verified = []
    KlineStore(database_runtime=installed_database_runtime).save(
        "BTC/USDT",
        "1h",
        [
            [1_700_000_000_000, 1, 1, 1, 1, 1],
            [1_700_007_200_000, 1, 1, 1, 1, 1],
        ],
    )
    service = DataHealthService(
        repository=DataHealthRepository(installed_database_runtime),
        database_verifier=lambda: verified.append(True),
        market_query_service=object(),
        index_data_service=object(),
        binance_market_service=SimpleNamespace(snapshot_service=StubSnapshot()),
        research_alert_runtime=object(),
        trade_signal_runtime=object(),
        cache_service=SimpleNamespace(
            runtime_backend="memory_fallback",
            local_entry_count=3,
            local_byte_size=256,
        ),
    )

    health = await service.get_health()
    repair = await service.repair(DataRepairCommand(action="verify_database"))

    from alembic.script import ScriptDirectory
    from app.infra.db.schema_runtime import _alembic_config

    assert health.databaseRevision == ScriptDirectory.from_config(
        _alembic_config(installed_database_runtime.database_url)).get_current_head()
    assert any(source.id == "database" for source in health.sources)
    kline_source = next(source for source in health.sources if source.id == "klines")
    assert kline_source.gapCount == 1
    assert kline_source.coverageStart is not None
    assert next(source for source in health.sources if source.id == "runtime_cache").metadata["backend"] == "memory_fallback"
    assert repair.status == "completed"
    assert verified == [True]
