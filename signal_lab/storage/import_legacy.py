from __future__ import annotations

from contextlib import closing
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
from shutil import copy2, disk_usage
import sqlite3

from signal_lab.storage.catalog_schema import SCHEMA_VERSION, schema_differences
from signal_lab.storage.codec import utc_now
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.paths import resolve_managed_path
from signal_lab.storage.sql import TABLES


_MARKER = "opentrading.signal_lab_market_data_import.v1"
_ARTIFACT_DIRS = ("raw", "exports")
_BATCH_SIZE = 2000
_LIQUIDITY_JOBS = "SELECT job_id FROM jobs WHERE task = 'liquidity_refresh'"
_LIQUIDITY_RUNS = "SELECT run_id FROM job_runs WHERE task = 'liquidity_refresh'"
_SOURCE_FILTERS = {
    "application_metadata": "WHERE key <> 'allocation_input_inspection'",
    "jobs": "WHERE task = 'liquidity_refresh'",
    "job_occurrences": f"WHERE job_id IN ({_LIQUIDITY_JOBS})",
    "job_runs": f"WHERE run_id IN ({_LIQUIDITY_RUNS})",
    "task_leases": f"WHERE owner_run_id IN ({_LIQUIDITY_RUNS})",
    "operation_events": (
        "WHERE (component NOT IN ('operations.scheduler', 'web.api')) "
        f"OR correlation_id IN ({_LIQUIDITY_RUNS}) "
        f"OR parent_correlation_id IN ({_LIQUIDITY_RUNS})"
    ),
}


def import_legacy_data(source_root: Path, target_root: Path, *, apply: bool) -> dict:
    source_root = source_root.resolve()
    database_file = source_root / "signal_lab.sqlite3"
    if not database_file.is_file():
        raise ValueError("源目录中找不到 signal_lab.sqlite3")
    target = SignalLabDatabase(target_root)
    if target.root.is_relative_to(source_root) or source_root.is_relative_to(target.root):
        raise ValueError("源数据目录和目标产物目录必须独立")

    with closing(sqlite3.connect(f"{database_file.as_uri()}?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        if source.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise ValueError("请使用 Signal Lab schema v6 作为迁移源")
        if schema_differences(database_file) or source.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("源数据库结构或关联记录有误")
        files = _artifact_inventory(source_root, target.root)
        for (reference,) in source.execute("SELECT relative_path FROM raw_snapshots"):
            path = resolve_managed_path(source_root, reference)
            if not path.is_file() or not path.is_relative_to(source_root / "raw"):
                raise ValueError(f"源数据库引用的原始响应不存在: {reference}")
        identity, counts = _record_inventory(source)
        plan = {"source_sha256": identity, "rows": counts, "files": len(files),
                "bytes": sum(size for _, _, size in files), "target": target.location,
                "artifact_root": str(target.root)}
        with target.connect() as connection:
            if apply:
                connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT value_json FROM application_metadata WHERE key = ?", (_MARKER,),
            ).fetchone()
            if existing is not None:
                if json.loads(existing[0])["source_sha256"] != identity:
                    raise ValueError("当前数据库已经导入过另一份 Signal Lab 数据")
                if apply:
                    _copy_artifacts(files, target.root)
                return {**plan, "status": "already_imported"}
            occupied = [table for table in TABLES if connection.execute(
                f"SELECT 1 FROM {table} LIMIT 1",
            ).fetchone()]
            if occupied:
                raise ValueError("目标库已有 Signal Lab 记录，迁移未覆盖已有记录: " + ", ".join(occupied))
            if not apply:
                return {**plan, "status": "ready"}
            _copy_artifacts(files, target.root)
            for table in TABLES:
                _copy_table(source, connection, table, counts[table])
            connection.sync_event_sequence()
            connection.execute(
                "INSERT INTO application_metadata(key, value_json, updated_at) VALUES (?, ?, ?)",
                (_MARKER, json.dumps(plan, sort_keys=True), utc_now()),
            )
        return {**plan, "status": "imported"}


def _record_inventory(source: sqlite3.Connection) -> tuple[str, dict[str, int]]:
    digest = sha256()
    counts = {}
    for table in TABLES:
        columns = source.execute(f"PRAGMA table_info({table})").fetchall()
        keys = sorted((col for col in columns if col[5]), key=lambda col: col[5])
        order = ", ".join(f'"{col[1]}"' for col in keys)
        digest.update(table.encode("ascii"))
        count = 0
        for row in source.execute(f"SELECT * FROM {table} {_SOURCE_FILTERS.get(table, '')} ORDER BY {order}"):
            digest.update(json.dumps(row, ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n")
            count += 1
        counts[table] = count
    return digest.hexdigest(), counts


def _copy_table(source, target, name: str, count: int) -> None:
    cursor = source.execute(f"SELECT * FROM {name} {_SOURCE_FILTERS.get(name, '')}")
    columns = ", ".join(f'"{column[0]}"' for column in cursor.description)
    placeholders = ", ".join("?" for _ in cursor.description)
    statement = f"INSERT INTO {name} ({columns}) VALUES ({placeholders})"
    while rows := cursor.fetchmany(_BATCH_SIZE):
        target.executemany(statement, rows)
    if target.execute(f"SELECT count(*) FROM {name}").fetchone()[0] != count:
        raise ValueError(f"记录数量校验失败: {name}")


def _artifact_inventory(source: Path, target: Path) -> list[tuple[Path, Path, int]]:
    files = []
    for name in _ARTIFACT_DIRS:
        for path in sorted((source / name).rglob("*")):
            if path.is_symlink() or not path.resolve().is_relative_to(source):
                raise ValueError(f"不支持迁移链接文件: {path}")
            if path.is_file():
                destination = target / path.relative_to(source)
                if not destination.resolve().is_relative_to(target):
                    raise ValueError(f"目标产物路径超出目录: {destination}")
                files.append((path, destination, path.stat().st_size))
    return files


def _copy_artifacts(files: list[tuple[Path, Path, int]], root: Path) -> None:
    target_volume = next(path for path in (root, *root.parents) if path.exists())
    needed = sum(size for _, target, size in files if not target.exists())
    if needed > disk_usage(target_volume).free:
        raise ValueError(f"产物目录磁盘空间不足，需要 {needed} 字节")
    for source, target, size in files:
        expected = _hash(source)
        if target.exists():
            if target.stat().st_size != size or _hash(target) != expected:
                raise ValueError(f"目标产物内容冲突: {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = target.with_name(f".{target.name}.signal-lab-import")
        copy2(source, staged)
        if staged.stat().st_size != size or _hash(staged) != expected:
            raise ValueError(f"复制产物校验失败: {source}")
        os.replace(staged, target)


def _hash(path: Path) -> str:
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()
