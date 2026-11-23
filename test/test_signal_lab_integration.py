from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.infra.db.database import build_database_runtime
from app.infra.db.schema_runtime import prepare_db, verify_database_schema
from app.main import create_app
from app.services.signal_lab_runtime import SignalLabRuntime
from config.settings import AppSettings
from signal_lab.operations import scheduler
from signal_lab.storage.catalog_schema import SCHEMA_SQL, SCHEMA_VERSION
from signal_lab.storage.import_legacy import import_legacy_data


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
    database = build_database_runtime(AppSettings(DATABASE_URL=f"sqlite:///{tmp_path / 'open.db'}"))
    try:
        prepare_db(database)
        verify_database_schema(database)
        runtime = SignalLabRuntime(database)
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
        app.state.runtime_services = SimpleNamespace(infra=SimpleNamespace(signal_lab=runtime))
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
