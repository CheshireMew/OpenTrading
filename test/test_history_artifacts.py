from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.domain.market.history.models import PriceBar
from app.infra.market_data.providers import ProviderFetch
from app.infra.persistence.market.history.artifact_publication import ArtifactPublisher
from app.infra.persistence.market.history.capacity import OPERATION_MANIFEST
from app.services.market.history.datasets import PriceDatasetService
from app.services.market.history.prices import PriceService
from app.services.market_data_runtime import MarketDataRuntime
from config.settings import AppSettings


def test_daily_artifacts_and_datasets_use_explicit_shared_dependencies(installed_database_runtime, tmp_path):
    settings = AppSettings(_env_file=None, MARKET_DATA_DIR=tmp_path / "history", MARKET_DATA_MIN_FREE_BYTES=1)
    runtime = MarketDataRuntime(installed_database_runtime, settings)
    calls = []

    def fetch(instrument, provider_symbol, start, end):
        calls.append((start, end))
        bars = tuple(PriceBar(datetime.combine(day, datetime.min.time(), timezone.utc),
                              open=100+i, high=103+i, low=99+i, close=101+i, adjusted_close=101+i, volume=100)
                     for i in range((end-start).days+1) if (day := start+timedelta(days=i)).weekday() < 5)
        return ProviderFetch("yfinance", provider_symbol, {"provider": "test"}, bars)

    prices = PriceService(runtime.database, runtime.config, provider_builder=lambda *a, **k: SimpleNamespace(fetch=fetch))
    datasets = PriceDatasetService(runtime.database, runtime.config, prices=prices,
                                   indicators=runtime.indicators, classifications=runtime.classifications)
    first, last = date(2024, 1, 2), date(2024, 1, 5)
    result = datasets.build("shared", ["SPY.US"], start=first, end=last, basis="raw", provider="yfinance")
    again = datasets.build("shared", ["SPY.US"], start=first, end=last, basis="raw", provider="yfinance")
    assert result == again and result["row_count"] == 4
    assert len(calls) == 1
    assert runtime.datasets.prices is runtime.prices
    assert runtime.datasets.indicators is runtime.indicators
    assert runtime.datasets.classifications is runtime.classifications
    from pathlib import Path
    assert (Path(result["manifest_path"]).parent / OPERATION_MANIFEST).is_file()
    point = prices.point("SPY.US", date(2024, 1, 3), policy="exact", cache_only=True, provider="yfinance")
    assert point["status"] == "ok" and point["statistics"]["close"] == 102
    comparison = prices.compare(["SPY.US", "QQQ.US"], start=first, end=last, provider="yfinance", export="csv")
    assert comparison["status"] == "ok" and comparison["artifact"]["rows"] == 4
    assert comparison["statistics"]["SPY.US"]["first"] == comparison["statistics"]["QQQ.US"]["first"] == 100


def test_shared_publisher_preserves_existing_files_and_rejects_changed_values(installed_database_runtime, tmp_path):
    runtime = MarketDataRuntime(installed_database_runtime, AppSettings(_env_file=None, MARKET_DATA_DIR=tmp_path / "history", MARKET_DATA_MIN_FREE_BYTES=1))
    publisher = ArtifactPublisher(runtime.database.root, runtime.config)
    destination = runtime.database.root / "exports" / "probe.parquet"
    frame = pd.DataFrame({"value": [1.0, 2.0]})
    options = dict(producer="probe", operation_id="probe", metadata={b"identity": b"probe"}, estimated_peak_bytes=4096, export="csv")
    exported = publisher.table(frame, destination, **options)
    stamp = destination.stat().st_mtime_ns
    assert publisher.table(frame, destination, **options) == exported
    assert destination.stat().st_mtime_ns == stamp
    with pytest.raises(ValueError, match="content mismatch"):
        publisher.table(pd.DataFrame({"value": [1.0, 3.0]}), destination, **options)


def test_shared_publisher_records_failed_writes(installed_database_runtime, tmp_path, monkeypatch):
    import json
    import app.infra.persistence.market.history.artifact_publication as module
    runtime = MarketDataRuntime(installed_database_runtime, AppSettings(_env_file=None, MARKET_DATA_DIR=tmp_path / "history", MARKET_DATA_MIN_FREE_BYTES=1))
    publisher = ArtifactPublisher(runtime.database.root, runtime.config)
    def fail(*args, **kwargs):
        raise OSError("controlled write failure")
    monkeypatch.setattr(module.pq, "write_table", fail)
    destination = runtime.database.root / "exports" / "probe.parquet"
    with pytest.raises(OSError, match="controlled write failure"):
        publisher.table(pd.DataFrame({"value": [1.0]}), destination, producer="probe", operation_id="failure",
                        metadata={}, estimated_peak_bytes=4096)
    operation = publisher.storage.operation_directory("probe", "failure") / OPERATION_MANIFEST
    assert json.loads(operation.read_text(encoding="utf-8"))["status"] == "failed"
    assert not destination.exists()


def test_macro_history_reuses_explicit_database_and_common_export_publisher(installed_database_runtime, tmp_path):
    from app.services.market.history.macro import MacroService
    calls = []
    def get_json(*args, **kwargs):
        calls.append(args)
        return {"observations": [{"date": "2024-01-02", "value": "4.1"}, {"date": "2024-01-03", "value": "4.2"}]}
    settings = AppSettings(_env_file=None, MARKET_DATA_DIR=tmp_path / "history", MARKET_DATA_MIN_FREE_BYTES=1, FRED_API_KEY="test")
    runtime = MarketDataRuntime(installed_database_runtime, settings)
    service = MacroService(runtime.database, runtime.config, transport=SimpleNamespace(get_json=get_json))
    args = dict(start=date(2024, 1, 2), end=date(2024, 1, 3), export="json")
    first = service.history("FRED:DGS10", **args)
    second = service.history("FRED:DGS10", cache_only=True, **args)
    assert first["status"] == second["status"] == "ok", (first, second)
    assert first["artifact"] == second["artifact"]
    assert first["artifact"]["rows"] == 2
    assert len(calls) == 1
