from contextlib import closing
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import inspect
from typer.testing import CliRunner

import config as application_config
from app.infra.db.database import build_database_runtime
from app.infra.db.schema_runtime import prepare_db, verify_database_schema
from app.main import create_app
from app.services.market_data_runtime import MarketDataRuntime
from config.settings import AppSettings
from config.market_data import MarketDataConfig
from app.services.market import history_jobs as scheduler
from app.infra.persistence.market.history.catalog_schema import SCHEMA_SQL, SCHEMA_VERSION
from app.infra.persistence.market.history.import_legacy import import_legacy_data
from scripts.market_data_cli import app as market_data_cli


def test_app_settings_keep_existing_data_paths_and_support_legacy_overrides(tmp_path, monkeypatch):
    for name in ("MARKET_DATA_DIR", "SIGNAL_LAB_DATA_DIR", "MARKET_DATA_MAX_MANAGED_BYTES",
                 "SIGNAL_LAB_MAX_MANAGED_BYTES", "MARKET_DATA_MIN_FREE_BYTES", "SIGNAL_LAB_MIN_FREE_BYTES"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "runtime"
    assert MarketDataConfig.from_settings(AppSettings(_env_file=None, RUNTIME_ROOT_DIR=root)).data_dir == root / "signal-lab"

    legacy = tmp_path / "existing-market-files"
    monkeypatch.setenv("SIGNAL_LAB_DATA_DIR", str(legacy))
    monkeypatch.setenv("SIGNAL_LAB_MAX_MANAGED_BYTES", "123456")
    legacy_config = MarketDataConfig.from_settings(AppSettings(_env_file=None, RUNTIME_ROOT_DIR=root))
    assert legacy_config.data_dir == legacy
    assert legacy_config.max_managed_bytes == 123456

    selected = tmp_path / "selected-market-files"
    monkeypatch.setenv("MARKET_DATA_DIR", str(selected))
    monkeypatch.setenv("MARKET_DATA_MAX_MANAGED_BYTES", "234567")
    selected_config = MarketDataConfig.from_settings(AppSettings(_env_file=None, RUNTIME_ROOT_DIR=root))
    assert selected_config.data_dir == selected
    assert selected_config.max_managed_bytes == 234567


def test_cli_and_http_share_the_application_database(installed_database_runtime, tmp_path, monkeypatch):
    settings = AppSettings(_env_file=None, DATABASE_URL=installed_database_runtime.database_url,
                           MARKET_DATA_DIR=tmp_path / "artifacts")
    monkeypatch.setattr(application_config, "settings", settings)
    runtime = MarketDataRuntime(installed_database_runtime, settings)
    result = CliRunner().invoke(market_data_cli, ["instruments", "resolve", "SPY.US"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["instrument"]["canonical_code"] == "SPY.US"

    app = create_app("api")
    app.state.runtime_services = SimpleNamespace(infra=SimpleNamespace(market_data=runtime))
    response = TestClient(app).get("/api/v1/signal-lab/database")
    assert response.status_code == 200
    assert response.json()["counts"]["instruments"] > 0
    with installed_database_runtime.engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT canonical_code FROM signal_lab_instruments WHERE canonical_code = 'SPY.US'",
        ).scalar_one() == "SPY.US"


def test_legacy_import_keeps_data_and_liquidity_jobs(tmp_path: Path, monkeypatch):
    source = tmp_path / "legacy"
    source.mkdir()
    old_database = source / "signal_lab.sqlite3"
    with closing(sqlite3.connect(old_database)) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.executescript("""
            CREATE TABLE research_runs (run_id TEXT PRIMARY KEY);
            INSERT INTO research_runs VALUES ('legacy-run');
            INSERT INTO instruments (
                canonical_code, name, asset_class, market, exchange_code, currency, timezone, updated_at
            ) VALUES ('SPY.US', 'SPDR S&P 500', 'etf', 'US', 'XNYS', 'USD', 'America/New_York', '2026-01-03');
            INSERT INTO jobs (job_id, task, interval_minutes, enabled, created_at, updated_at, next_run_at)
            VALUES ('liquidity', 'liquidity_refresh', 240, 1, '2026-01-03', '2026-01-03', '2026-01-04'),
                   ('allocation', 'allocation_refresh', 240, 1, '2026-01-03', '2026-01-03', '2026-01-04');
        """)
        connection.commit()

    (source / "raw").mkdir()
    (source / "raw" / "evidence.json").write_text("market evidence", encoding="utf-8")
    (source / "runs").mkdir()
    (source / "runs" / "report.html").write_text("older report", encoding="utf-8")

    output = tmp_path / "artifacts"
    monkeypatch.setenv("SIGNAL_LAB_DATA_DIR", str(output))
    settings = AppSettings(DATABASE_URL=f"sqlite:///{tmp_path / 'open.db'}")
    database = build_database_runtime(settings)
    try:
        prepare_db(database)
        verify_database_schema(database)
        runtime = MarketDataRuntime(database, settings)
        with runtime.bind():
            assert import_legacy_data(source, output, apply=False)["status"] == "ready"
            assert not output.exists()
            imported = import_legacy_data(source, output, apply=True)
            assert imported["status"] == "imported"
            assert imported["rows"]["jobs"] == 1
            assert import_legacy_data(source, output, apply=True)["status"] == "already_imported"

        assert (output / "raw" / "evidence.json").read_text(encoding="utf-8") == "market evidence"
        assert (source / "runs" / "report.html").is_file()
        assert not (output / "runs").exists()
        assert "signal_lab_research_runs" not in inspect(database.engine).get_table_names()
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT job_id FROM signal_lab_jobs").scalar_one() == "liquidity"

        app = create_app("api")
        app.state.runtime_services = SimpleNamespace(infra=SimpleNamespace(market_data=runtime))
        client = TestClient(app)
        response = client.get("/api/v1/signal-lab/database")
        assert response.status_code == 200
        assert response.json()["counts"]["instruments"] == 1
        assert client.get("/api/v1/signal-lab/runs").status_code == 404

        def refresh(root, config):
            assert root == config.data_dir == output
            return {"series_count": 13, "row_count": 2, "retrieved_at": "2026-01-04"}

        monkeypatch.setattr(scheduler, "sync_liquidity_data", refresh)
        response = client.post("/api/v1/signal-lab/liquidity/refresh")
        assert response.status_code == 200
        assert response.json()["run"]["status"] == "success"
        request_id = response.headers["X-Request-ID"]
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT result FROM signal_lab_operation_events WHERE correlation_id = ?", (request_id,),
            ).scalar_one() == "success"
    finally:
        database.dispose()
