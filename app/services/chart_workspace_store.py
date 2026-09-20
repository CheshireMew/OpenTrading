"""Versioned workspace documents. Deliberately separate from research records."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from app.contracts.chart_workspace import WorkspaceDocument, WorkspaceWrite

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT / ".heimdall_runtime" / "chart_workspace"


class WorkspaceConflict(ValueError):
    pass


class ChartWorkspaceStore:
    def __init__(self, root: Path = WORKSPACE_ROOT):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "workspace.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    kind TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
                    version INTEGER NOT NULL, data TEXT NOT NULL, updated_at INTEGER NOT NULL,
                    readonly INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS revisions (
                    kind TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(kind,id,version));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def document(row) -> WorkspaceDocument:
        return WorkspaceDocument(id=row["id"], name=row["name"], version=row["version"],
                                 data=json.loads(row["data"]), updated_at=row["updated_at"],
                                 readonly=bool(row["readonly"]))

    def list(self, kind: str) -> list[WorkspaceDocument]:
        with self.connect() as db:
            return [self.document(r) for r in db.execute(
                "SELECT * FROM documents WHERE kind=? AND archived=0 ORDER BY updated_at DESC,id", (kind,))]

    def get(self, kind: str, key: str, version: int | None = None) -> WorkspaceDocument:
        with self.connect() as db:
            if version is not None:
                row = db.execute("SELECT payload FROM revisions WHERE kind=? AND id=? AND version=?",
                                 (kind, key, version)).fetchone()
                if row:
                    return WorkspaceDocument.model_validate_json(row[0])
            else:
                row = db.execute("SELECT * FROM documents WHERE kind=? AND id=? AND archived=0", (kind, key)).fetchone()
                if row:
                    return self.document(row)
        raise KeyError(key)

    def put(self, kind: str, key: str, write: WorkspaceWrite, *, readonly=False) -> WorkspaceDocument:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM documents WHERE kind=? AND id=?", (kind, key)).fetchone()
            if old and old["readonly"]:
                raise WorkspaceConflict("原版脚本只读，请另存副本")
            if (old["version"] if old else 0) != write.expected_version:
                raise WorkspaceConflict("内容已在另一窗口更新，请重新载入后保存；本地草稿仍保留")
            doc = WorkspaceDocument(id=key, name=write.name, data=write.data,
                version=write.expected_version + 1, updated_at=int(time.time() * 1000), readonly=readonly)
            db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,0)",
                (kind, key, doc.name, doc.version, json.dumps(doc.data, ensure_ascii=False), doc.updated_at, int(readonly)))
            db.execute("INSERT INTO revisions VALUES (?,?,?,?)", (kind, key, doc.version, doc.model_dump_json()))
            return doc

    def archive(self, kind: str, key: str):
        with self.connect() as db:
            row = db.execute("SELECT readonly FROM documents WHERE kind=? AND id=?", (kind,key)).fetchone()
            if not row:
                raise KeyError(key)
            if row[0]:
                raise WorkspaceConflict("原版脚本只读")
            db.execute("UPDATE documents SET archived=1 WHERE kind=? AND id=?", (kind,key))

    def seed(self):
        try:
            self.get("scripts", "heimdall-v7-2")
        except KeyError:
            self.put("scripts", "heimdall-v7-2", WorkspaceWrite(name="Heimdall ETH · EMA55 · v7.2",
                data={"source": (ROOT / "strategies/pine/eth_ema55_manual_chart_v7_2.pine").read_text(encoding="utf-8"),
                      "language": "pine", "kind": "indicator"}), readonly=True)
        if not self.list("watchlists"):
            self.put("watchlists", "default", WorkspaceWrite(name="我的自选", data={"symbols": [
                "binance:spot:BTCUSDT", "binance:spot:ETHUSDT", "binance:spot:SOLUSDT"]}))
