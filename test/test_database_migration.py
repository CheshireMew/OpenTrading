from __future__ import annotations

import json
from datetime import datetime

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.infra.db.database import build_database_runtime, resolve_database_url
import app.infra.db.schema_runtime as schema_runtime
from app.infra.db.schema import Base
from config.settings import AppSettings


ALEMBIC_VERSION_NUM_LIMIT = 32


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    engines = []
    runtimes = []

    def activate(name: str):
        path = tmp_path / name
        url = f"sqlite:///{path.as_posix()}"
        engine = create_engine(url, connect_args={"check_same_thread": False})
        engines.append(engine)
        runtime = build_database_runtime(AppSettings(DATABASE_URL=url))
        runtime.dispose()
        runtime.engine = engine
        runtime.session_factory.configure(bind=engine)
        runtimes.append(runtime)
        schema_runtime._prepared_urls.clear()
        return path, engine, runtime

    yield activate

    schema_runtime._prepared_urls.clear()
    for runtime in runtimes:
        runtime.dispose()
    for engine in engines:
        engine.dispose()


def test_prepare_db_initializes_empty_sqlite(isolated_db):
    _, engine, runtime = isolated_db("empty.db")
    schema_runtime.prepare_db(runtime)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert {table.name for table in Base.metadata.sorted_tables}.issubset(table_names)
    assert "backtest_runs" not in table_names
    assert "factor_datasets" not in table_names

    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    expected = ScriptDirectory.from_config(schema_runtime._alembic_config(runtime.database_url)).get_current_head()
    assert current == expected
    schema_runtime.verify_database_schema(runtime)


def test_alembic_revision_ids_fit_version_table():
    script = ScriptDirectory.from_config(schema_runtime._alembic_config("sqlite:///:memory:"))

    too_long = [
        revision.revision
        for revision in script.walk_revisions()
        if len(revision.revision) > ALEMBIC_VERSION_NUM_LIMIT
    ]

    assert too_long == []


def test_prepare_db_drops_archived_research_tables_from_previous_head(isolated_db):
    _, engine, runtime = isolated_db("previous_head.db")
    alembic_config = schema_runtime._alembic_config(runtime.database_url)
    command.upgrade(alembic_config, "006_backtest_preview_artifacts")
    schema_runtime._prepared_urls.clear()

    before_tables = set(inspect(engine).get_table_names())
    assert "backtest_runs" in before_tables
    assert "factor_datasets" in before_tables

    schema_runtime.prepare_db(runtime)

    table_names = set(inspect(engine).get_table_names())
    assert "backtest_runs" not in table_names
    assert "factor_datasets" not in table_names
    schema_runtime.verify_database_schema(runtime)


def test_portfolio_simulation_migration_is_lossless_and_reversible(isolated_db):
    _, engine, runtime = isolated_db("portfolio_simulation.db")
    alembic_config = schema_runtime._alembic_config(runtime.database_url)
    command.upgrade(alembic_config, "011_seed_portfolio_state")
    now = datetime(2026, 8, 24)
    simulation = {
        "startDate": "2026-01-01",
        "endDate": "2026-01-02",
        "initialValue": 100,
        "finalValue": 101,
        "totalReturnPct": 1,
        "annualizedReturnPct": 10,
        "maxDrawdownPct": 0,
        "reviewCount": 1,
        "outOfBandReviewCount": 0,
        "rebalanceCount": 0,
        "equityCurve": [],
    }
    payload = {
        "id": "core",
        "name": "Core",
        "assets": [{"symbol": "BTC", "targetWeight": 100}],
        "strategy": {"reviewFrequency": "monthly"},
        "simulation": {"initialCapital": 100, "simulationStartDate": "2026-01-01"},
        "lastSimulationResult": simulation,
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO portfolio_records "
                "(id, payload, version, position, deleted_at, created_at, updated_at) "
                "VALUES (:id, :payload, 1, 0, NULL, :created_at, :updated_at)"
            ),
            {
                "id": "core",
                "payload": json.dumps(payload),
                "created_at": now,
                "updated_at": now,
            },
        )

    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        migrated_payload = json.loads(
            connection.scalar(text("SELECT payload FROM portfolio_records WHERE id = 'core'"))
        )
        simulation_payload = json.loads(
            connection.scalar(
                text("SELECT payload FROM portfolio_simulation_results WHERE portfolio_id = 'core'")
            )
        )
    assert "lastSimulationResult" not in migrated_payload
    assert simulation_payload == simulation
    assert "ix_klines_timeframe_timestamp" in {
        item["name"] for item in inspect(engine).get_indexes("klines")
    }

    command.downgrade(alembic_config, "011_seed_portfolio_state")
    with engine.connect() as connection:
        restored_payload = json.loads(
            connection.scalar(text("SELECT payload FROM portfolio_records WHERE id = 'core'"))
        )
    assert restored_payload["lastSimulationResult"] == simulation


def test_prepare_db_rejects_unmanaged_nonempty_schema(isolated_db):
    _, engine, runtime = isolated_db("unmanaged.db")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unmanaged_table (id INTEGER)")

    with pytest.raises(RuntimeError, match="未纳入 Alembic 管理"):
        schema_runtime.prepare_db(runtime)


def test_verify_database_schema_rejects_stamped_but_incomplete_schema(isolated_db):
    _, engine, runtime = isolated_db("bad_stamp.db")
    head = ScriptDirectory.from_config(schema_runtime._alembic_config(runtime.database_url)).get_current_head()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.exec_driver_sql(
            f"INSERT INTO alembic_version VALUES ('{head}')"
        )
        for table in Base.metadata.sorted_tables:
            connection.exec_driver_sql(f"CREATE TABLE {table.name} (id INTEGER)")

    with pytest.raises(RuntimeError, match="数据库结构与当前模型不一致"):
        schema_runtime.verify_database_schema(runtime)


def test_database_resolution_requires_database_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        resolve_database_url(AppSettings(DATABASE_URL=""))

    explicit_url = "postgresql://postgres@localhost:5432/heimdall"
    database_url, source = resolve_database_url(AppSettings(DATABASE_URL=explicit_url))
    assert database_url == explicit_url
    assert source == "settings"
