"""Immutable Zstandard Parquet segments, preserving every original float and flag."""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
from shutil import disk_usage
import struct

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select

from app.infra.db.schema import KlineArchiveSegment

FIELDS = ("timestamp", "open", "high", "low", "close", "volume", "finalized")
ARCHIVE_LOCK_KEY = 485374620219
RECORD = struct.Struct("<q5d?")
SCHEMA = pa.schema([(name, pa.int64() if name == "timestamp" else
                     pa.bool_() if name == "finalized" else pa.float64()) for name in FIELDS])


def record_bytes(row) -> bytes:
    return RECORD.pack(int(row[0]), *(float(v) for v in row[1:6]), bool(row[6]))


def content_hash(symbol: str, timeframe: str, rows) -> str:
    digest = sha256(json.dumps([symbol, timeframe], separators=(",", ":")).encode())
    for row in rows:
        digest.update(record_bytes(row))
    return digest.hexdigest()


@lru_cache(maxsize=64)
def _verified_file(path: str, size: int, mtime_ns: int, file_hash: str) -> bool:
    with open(path, "rb") as stream:
        digest = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != file_hash:
        raise RuntimeError(f"K-line archive checksum mismatch: {path}")
    return True


class KlineArchive:
    def __init__(self, runtime):
        self.root = getattr(runtime, "archive_root", None)

    def _path(self, reference: str) -> Path:
        if self.root is None:
            raise RuntimeError("K-line archive directory is not configured")
        root = self.root.resolve()
        path = (root / reference).resolve()
        if not path.is_relative_to(root):
            raise RuntimeError("K-line archive path is outside its configured directory")
        return path

    def write_verified(self, symbol: str, timeframe: str, rows) -> KlineArchiveSegment:
        if not rows:
            raise ValueError("Cannot archive an empty batch")
        identity = content_hash(symbol, timeframe, rows)
        scope = sha256(json.dumps([symbol, timeframe]).encode()).hexdigest()[:24]
        reference = f"{scope}/{identity}.parquet"
        path = self._path(reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Keep bounded batches and fail before consuming the reserve needed for
        # verification and database maintenance. No copies of the full DB.
        if disk_usage(path.parent).free < max(64 * 1024 * 1024, len(rows) * 256):
            raise RuntimeError("Insufficient disk space for a verified K-line archive batch")
        if not path.exists():
            temporary = path.with_suffix(".parquet.pending")
            table = pa.Table.from_arrays(
                [pa.array([row[i] for row in rows], type=field.type) for i, field in enumerate(SCHEMA)],
                schema=SCHEMA,
            ).replace_schema_metadata({b"opentrading.kline_archive": b"1",
                                       b"symbol": symbol.encode(), b"timeframe": timeframe.encode(),
                                       b"content_sha256": identity.encode()})
            pq.write_table(table, temporary, compression="zstd", compression_level=9,
                           row_group_size=16_384, write_statistics=True)
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            temporary.replace(path)
        # Read the durable file back, checking every bit, before a DB row can move.
        restored = self.read_path(path)
        if len(restored) != len(rows) or content_hash(symbol, timeframe, restored) != identity:
            raise RuntimeError(f"K-line archive round-trip failed: {path}")
        for original, recovered in zip(rows, restored):
            if record_bytes(original) != record_bytes(recovered):
                raise RuntimeError(f"K-line archive changed an original value: {path}")
        return KlineArchiveSegment(
            id=identity, symbol=symbol, timeframe=timeframe,
            first_timestamp=int(rows[0][0]), last_timestamp=int(rows[-1][0]),
            row_count=len(rows), finalized_count=sum(bool(r[6]) for r in rows),
            relative_path=reference, file_sha256=sha256(path.read_bytes()).hexdigest(),
            size_bytes=path.stat().st_size,
        )

    @staticmethod
    def read_path(path: Path, *, start: int | None = None, end: int | None = None,
                  finalized_only: bool = False) -> list[tuple]:
        filters = []
        if start is not None:
            filters.append(("timestamp", ">=", start))
        if end is not None:
            filters.append(("timestamp", "<=", end))
        if finalized_only:
            filters.append(("finalized", "=", True))
        table = pq.ParquetFile(path).read() if not filters else pq.read_table(path, filters=filters)
        if table.schema.remove_metadata() != SCHEMA:
            raise RuntimeError(f"Unsupported K-line archive schema: {path}")
        columns = [table[name].to_pylist() for name in FIELDS]
        return list(zip(*columns))

    def read_segment(self, segment, *, start=None, end=None, finalized_only=False):
        path = self._path(segment.relative_path)
        info = path.stat()  # Missing files fail visibly; do not silently hide history.
        if info.st_size != segment.size_bytes:
            raise RuntimeError(f"K-line archive size mismatch: {path}")
        _verified_file(str(path), info.st_size, info.st_mtime_ns, segment.file_sha256)
        return self.read_path(path, start=start, end=end, finalized_only=finalized_only)

    def read(self, session, symbol: str, timeframe: str, start: int | None, end: int,
             *, finalized_only: bool = True, limit: int | None = None) -> list[tuple]:
        statement = select(KlineArchiveSegment).where(
            KlineArchiveSegment.symbol == symbol, KlineArchiveSegment.timeframe == timeframe,
            KlineArchiveSegment.first_timestamp <= end,
        )
        if start is not None:
            statement = statement.where(KlineArchiveSegment.last_timestamp >= start)
        segments = session.scalars(statement.order_by(KlineArchiveSegment.last_timestamp.desc())).all()
        if finalized_only:
            confirmed = [s for s in segments if s.finalized_count]
            if not confirmed:
                return []
            # A newer unconfirmed correction must mask an older confirmed row,
            # but unrelated all-unconfirmed segments need no file reads.
            segments = [s for s in segments if s.finalized_count or any(
                s.first_timestamp <= old.last_timestamp and s.last_timestamp >= old.first_timestamp
                for old in confirmed)]
        found, versions = {}, {}
        for segment in segments:
            if limit:
                valid = sorted(t for t, row in found.items() if not finalized_only or row[6])
                if len(valid) >= limit and segment.last_timestamp < valid[-limit]:
                    break
            version = (segment.archived_at, segment.id)
            for row in self.read_segment(segment, start=start, end=end):
                timestamp = int(row[0])
                if timestamp not in versions or version > versions[timestamp]:
                    found[timestamp], versions[timestamp] = row, version
        ordered = [found[timestamp] for timestamp in sorted(found)
                   if not finalized_only or found[timestamp][6]]
        return ordered[-limit:] if limit else ordered
