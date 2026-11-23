"""Index immutable run snapshots once; serve subsequent pages with indexed reads."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class PineRecordStore:
    def __init__(self, folder: Path):
        self.folder = folder
        self.path = folder / "records.sqlite3"

    def consume_report(self, stream):
        """Commit streamed results once, without keeping duplicate JSON files."""
        counts = {key: 0 for key in ("equity", "trades", "open_trades", "warnings")}
        completed = None
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("CREATE TABLE IF NOT EXISTS records(kind TEXT, ordinal INTEGER, payload TEXT, PRIMARY KEY(kind,ordinal))")
            db.execute("CREATE TABLE IF NOT EXISTS totals(kind TEXT PRIMARY KEY, count INTEGER NOT NULL)")
            for line in stream:
                if not line.startswith(b"OPENTRADING_REPORT\t"):
                    continue
                frame = json.loads(line.split(b"\t", 1)[1])
                kind = frame["kind"]
                if kind == "summary":
                    completed = (frame["summary"], frame["provenance"])
                elif kind in counts:
                    offset = counts[kind]
                    db.executemany("INSERT INTO records VALUES(?,?,?)", (
                        (kind, offset + index, json.dumps(row, ensure_ascii=False, allow_nan=False))
                        for index, row in enumerate(frame["items"])))
                    counts[kind] += len(frame["items"])
                else:
                    raise ValueError("回测报告包含未知记录类型")
            if completed is None:
                raise ValueError("回测进程未返回完整报告")
            db.executemany("INSERT INTO totals VALUES(?,?)", counts.items())
        return completed

    def page(self, kind: str, offset: int, limit: int) -> dict:
        if offset < 0 or not 1 <= limit <= 10000:
            raise ValueError("记录分页范围无效")
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute("CREATE TABLE IF NOT EXISTS records(kind TEXT, ordinal INTEGER, payload TEXT, PRIMARY KEY(kind,ordinal))")
            db.execute("CREATE TABLE IF NOT EXISTS sources(name TEXT PRIMARY KEY, identity TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS totals(kind TEXT PRIMARY KEY, count INTEGER NOT NULL)")
            # The write lock also serializes concurrent first access to a legacy run.
            db.execute("BEGIN IMMEDIATE")
            for name in ("input", "result"):
                source = self.folder / f"{name}.json"
                if not source.exists():
                    continue
                stat = source.stat()
                identity = f"{stat.st_size}:{stat.st_mtime_ns}"
                previous = db.execute("SELECT identity FROM sources WHERE name=?", (name,)).fetchone()
                if previous and previous[0] == identity:
                    continue
                payload = json.loads(source.read_text(encoding="utf-8"))
                groups = {"bars": payload.get("bars", [])} if name == "input" else {
                    key: payload.get(key, []) for key in ("equity", "trades", "open_trades", "orders", "fills", "warnings")
                }
                for key, rows in groups.items():
                    db.execute("DELETE FROM records WHERE kind=?", (key,))
                    db.executemany("INSERT INTO records VALUES(?,?,?)", ((key, index, json.dumps(row, ensure_ascii=False, allow_nan=False)) for index, row in enumerate(rows)))
                    db.execute("INSERT OR REPLACE INTO totals VALUES(?,?)", (key, len(rows)))
                db.execute("INSERT OR REPLACE INTO sources VALUES(?,?)", (name, identity))
            db.commit()
            total = db.execute("SELECT count FROM totals WHERE kind=?", (kind,)).fetchone()
            rows = db.execute("SELECT payload FROM records WHERE kind=? AND ordinal>=? ORDER BY ordinal LIMIT ?", (kind, offset, limit))
            return {"items": [json.loads(row[0]) for row in rows], "total": total[0] if total else 0, "offset": offset}

    def sampled_equity(self, limit: int) -> dict:
        total = self.page("equity", 0, 1)["total"]
        width = max(1, (total + max(1, limit // 4) - 1) // max(1, limit // 4))
        selected, bucket = [], []

        def flush():
            if bucket:
                indices = {0, len(bucket) - 1,
                           min(range(len(bucket)), key=lambda i: bucket[i]["equity"]),
                           max(range(len(bucket)), key=lambda i: bucket[i]["equity"])}
                selected.extend(bucket[i] for i in sorted(indices))
                bucket.clear()

        with sqlite3.connect(self.path, timeout=30) as db:
            for (payload,) in db.execute("SELECT payload FROM records WHERE kind='equity' ORDER BY ordinal"):
                bucket.append(json.loads(payload))
                if len(bucket) >= width:
                    flush()
        flush()
        return {"items": selected, "total": total, "offset": 0}
