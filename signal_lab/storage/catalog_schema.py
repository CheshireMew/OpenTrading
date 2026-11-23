from __future__ import annotations

from pathlib import Path
import sqlite3


SCHEMA_VERSION = 6


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_metadata (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_snapshots (
    snapshot_hash TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    resource TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_snapshot_acquisitions (
    acquisition_id TEXT PRIMARY KEY,
    snapshot_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    resource TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (snapshot_hash) REFERENCES raw_snapshots(snapshot_hash)
);

CREATE INDEX IF NOT EXISTS ix_raw_snapshot_acquisitions_content
    ON raw_snapshot_acquisitions(snapshot_hash, retrieved_at, acquisition_id);

CREATE TABLE IF NOT EXISTS instruments (
    canonical_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    market TEXT NOT NULL,
    exchange_code TEXT NOT NULL,
    currency TEXT NOT NULL,
    timezone TEXT NOT NULL,
    listed_on TEXT,
    is_continuous INTEGER NOT NULL DEFAULT 0 CHECK (is_continuous IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instrument_aliases (
    normalized_alias TEXT NOT NULL,
    alias TEXT NOT NULL,
    canonical_code TEXT NOT NULL,
    alias_kind TEXT NOT NULL,
    PRIMARY KEY (normalized_alias, canonical_code),
    FOREIGN KEY (canonical_code) REFERENCES instruments(canonical_code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_instrument_alias_lookup
    ON instrument_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS provider_mappings (
    canonical_code TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (canonical_code, provider),
    FOREIGN KEY (canonical_code) REFERENCES instruments(canonical_code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    snapshot_hash TEXT PRIMARY KEY,
    canonical_code TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    actual_start TEXT,
    actual_end TEXT,
    retrieved_at TEXT NOT NULL,
    source_snapshot_hash TEXT NOT NULL,
    price_basis TEXT NOT NULL,
    coverage_status TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    is_latest INTEGER NOT NULL DEFAULT 0 CHECK (is_latest IN (0, 1)),
    identity_version INTEGER NOT NULL DEFAULT 1 CHECK (identity_version IN (1, 2)),
    FOREIGN KEY (canonical_code) REFERENCES instruments(canonical_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_price_snapshot_scope_latest
    ON price_snapshots(
        canonical_code, timeframe, provider, requested_start, requested_end
    ) WHERE is_latest = 1;

CREATE INDEX IF NOT EXISTS ix_price_snapshot_lookup
    ON price_snapshots(canonical_code, timeframe, requested_start, requested_end, retrieved_at);

CREATE TABLE IF NOT EXISTS price_bars (
    snapshot_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    adjusted_close REAL NOT NULL,
    volume REAL,
    dividend REAL NOT NULL DEFAULT 0,
    split_factor REAL NOT NULL DEFAULT 1,
    PRIMARY KEY (snapshot_hash, observed_at),
    FOREIGN KEY (snapshot_hash) REFERENCES price_snapshots(snapshot_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_price_bars_range
    ON price_bars(snapshot_hash, observation_date);

CREATE TABLE IF NOT EXISTS coverage_issues (
    snapshot_hash TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    issue_date TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL,
    PRIMARY KEY (snapshot_hash, issue_type, issue_date, detail),
    FOREIGN KEY (snapshot_hash) REFERENCES price_snapshots(snapshot_hash) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS snapshot_bundle_imports (
    import_id TEXT PRIMARY KEY,
    bundle_hash TEXT NOT NULL,
    bundle_path TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'ok', 'failed')),
    snapshot_count INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS classification_snapshots (
    snapshot_hash TEXT PRIMARY KEY,
    scheme_id TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    scheme_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    source_snapshot_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    is_latest INTEGER NOT NULL DEFAULT 0 CHECK (is_latest IN (0, 1))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_classification_scheme_latest
    ON classification_snapshots(scheme_id) WHERE is_latest = 1;

CREATE TABLE IF NOT EXISTS classifications (
    snapshot_hash TEXT NOT NULL,
    classification_id TEXT NOT NULL,
    name TEXT NOT NULL,
    parent_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (snapshot_hash, classification_id),
    FOREIGN KEY (snapshot_hash) REFERENCES classification_snapshots(snapshot_hash) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS classification_memberships (
    snapshot_hash TEXT NOT NULL,
    classification_id TEXT NOT NULL,
    canonical_code TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (snapshot_hash, classification_id, canonical_code, valid_from),
    FOREIGN KEY (snapshot_hash, classification_id)
        REFERENCES classifications(snapshot_hash, classification_id) ON DELETE CASCADE,
    FOREIGN KEY (canonical_code) REFERENCES instruments(canonical_code)
);

CREATE INDEX IF NOT EXISTS ix_classification_membership_asof
    ON classification_memberships(canonical_code, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS price_datasets (
    dataset_hash TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    basis TEXT NOT NULL,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    created_at TEXT NOT NULL,
    manifest_relative_path TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    instrument_count INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS price_dataset_members (
    dataset_hash TEXT NOT NULL,
    canonical_code TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    partition_relative_path TEXT NOT NULL,
    PRIMARY KEY (dataset_hash, canonical_code),
    FOREIGN KEY (dataset_hash) REFERENCES price_datasets(dataset_hash) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_hash) REFERENCES price_snapshots(snapshot_hash),
    FOREIGN KEY (canonical_code) REFERENCES instruments(canonical_code)
);

CREATE TABLE IF NOT EXISTS macro_history_snapshots (
    snapshot_hash TEXT PRIMARY KEY,
    series_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    actual_start TEXT,
    actual_end TEXT,
    retrieved_at TEXT NOT NULL,
    source_snapshot_hash TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    is_latest INTEGER NOT NULL DEFAULT 0 CHECK (is_latest IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_history_latest
    ON macro_history_snapshots(series_id) WHERE is_latest = 1;

CREATE TABLE IF NOT EXISTS macro_history_values (
    snapshot_hash TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    value REAL NOT NULL,
    realtime_start TEXT,
    realtime_end TEXT,
    PRIMARY KEY (snapshot_hash, observation_date),
    FOREIGN KEY (snapshot_hash) REFERENCES macro_history_snapshots(snapshot_hash) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS indicator_series (
    indicator_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_series_id TEXT,
    name TEXT NOT NULL,
    short_label TEXT NOT NULL,
    category TEXT NOT NULL,
    group_id TEXT NOT NULL,
    group_label TEXT NOT NULL,
    unit TEXT NOT NULL,
    frequency TEXT NOT NULL,
    polarity TEXT NOT NULL,
    description TEXT NOT NULL,
    is_scored INTEGER NOT NULL CHECK (is_scored IN (0, 1)),
    raw_weight REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS indicator_observations (
    indicator_id TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    value REAL NOT NULL,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    PRIMARY KEY (indicator_id, observation_date),
    FOREIGN KEY (indicator_id)
        REFERENCES indicator_series(indicator_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_indicator_history
    ON indicator_observations(indicator_id, observation_date);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    next_run_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS job_occurrences (
    occurrence_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    job_version INTEGER NOT NULL,
    scheduled_at TEXT NOT NULL,
    trigger TEXT NOT NULL CHECK (trigger IN ('scheduled', 'manual')),
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'running', 'success', 'warning', 'blocked', 'error',
            'interrupted', 'cancelled'
        )
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

CREATE INDEX IF NOT EXISTS ix_job_occurrences_due
    ON job_occurrences(job_id, scheduled_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ux_job_scheduled_occurrence
    ON job_occurrences(job_id, job_version, scheduled_at) WHERE trigger = 'scheduled';

CREATE TABLE IF NOT EXISTS job_runs (
    run_id TEXT PRIMARY KEY,
    occurrence_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    job_id TEXT NOT NULL,
    task TEXT NOT NULL,
    worker_id TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'running', 'success', 'warning', 'blocked', 'error',
            'interrupted', 'cancelled'
        )
    ),
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL,
    UNIQUE(occurrence_id, attempt),
    FOREIGN KEY (occurrence_id) REFERENCES job_occurrences(occurrence_id),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);

CREATE INDEX IF NOT EXISTS ix_job_runs_latest
    ON job_runs(job_id, started_at DESC);

CREATE INDEX IF NOT EXISTS ix_job_runs_lease
    ON job_runs(status, lease_expires_at);

CREATE TABLE IF NOT EXISTS task_leases (
    task TEXT PRIMARY KEY,
    owner_run_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    FOREIGN KEY (owner_run_id) REFERENCES job_runs(run_id)
);

CREATE TABLE IF NOT EXISTS operation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    event TEXT NOT NULL,
    result TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    parent_correlation_id TEXT,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_operation_events_correlation
    ON operation_events(correlation_id, event_id);
"""


class DatabaseSchemaError(RuntimeError):
    """Raised when a same-version database no longer matches the managed schema."""


def schema_differences(path: Path) -> list[str]:
    expected = sqlite3.connect(":memory:")
    actual = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0)
    try:
        expected.executescript(SCHEMA_SQL)
        expected_contract = _schema_contract(expected)
        actual_contract = _schema_contract(actual)
    finally:
        expected.close()
        actual.close()
    differences: list[str] = []
    expected_tables = set(expected_contract)
    actual_tables = set(actual_contract)
    if missing := sorted(expected_tables - actual_tables):
        differences.append(f"missing tables={missing}")
    for table in sorted(expected_tables & actual_tables):
        expected_item = expected_contract[table]
        actual_item = actual_contract[table]
        for key in ("columns", "foreign_keys", "constraints", "indexes"):
            if expected_item[key] != actual_item[key]:
                differences.append(f"{table}.{key} differs")
    return differences


def _schema_contract(connection: sqlite3.Connection) -> dict[str, dict[str, tuple]]:
    tables = [
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]
    contract: dict[str, dict[str, tuple]] = {}
    for table in tables:
        quoted = table.replace('"', '""')
        columns = tuple(sorted(
            (tuple(row[1:7]) for row in connection.execute(
                f'PRAGMA table_xinfo("{quoted}")'
            ).fetchall()),
            key=lambda item: item[0],
        ))
        foreign_keys = tuple(sorted(
            (
                (row[2], row[3], row[4], row[5], row[6], row[7], row[1])
                for row in connection.execute(
                    f'PRAGMA foreign_key_list("{quoted}")'
                ).fetchall()
            ),
            key=repr,
        ))
        constraints = []
        indexes = []
        for row in connection.execute(f'PRAGMA index_list("{quoted}")').fetchall():
            name, unique, origin, partial = row[1], row[2], row[3], row[4]
            index_quoted = name.replace('"', '""')
            columns_in_index = tuple(
                item[2]
                for item in connection.execute(f'PRAGMA index_info("{index_quoted}")').fetchall()
            )
            value = (origin, int(unique), int(partial), columns_in_index)
            if origin in {"pk", "u"}:
                constraints.append(value)
            elif not name.startswith("sqlite_autoindex"):
                indexes.append((name, *value))
        contract[table] = {
            "columns": columns,
            "foreign_keys": foreign_keys,
            "constraints": tuple(sorted(constraints, key=repr)),
            "indexes": tuple(sorted(indexes, key=repr)),
        }
    return contract
