"""Immutable Zstandard Parquet segments, preserving every original float and flag."""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from itertools import groupby
import json
import os
from pathlib import Path
from shutil import disk_usage
import struct

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import BigInteger, Boolean, Column, MetaData, Table, delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db.schema import Kline, KlineArchiveSegment

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

    def _segment_path(self, segment):
        path = self._path(segment.relative_path)
        info = path.stat()  # Missing files fail visibly; do not silently hide history.
        if info.st_size != segment.size_bytes:
            raise RuntimeError(f"K-line archive size mismatch: {path}")
        return path

    def read_segment(self, segment, *, start=None, end=None, finalized_only=False):
        path = self._segment_path(segment)
        info = path.stat()
        _verified_file(str(path), info.st_size, info.st_mtime_ns, segment.file_sha256)
        return self.read_path(path, start=start, end=end, finalized_only=finalized_only)

    def _coverage_flags(self, segment):
        """Stream only identity/visibility columns for overlapping corrections."""
        file = pq.ParquetFile(self._segment_path(segment))
        try:
            if file.schema_arrow.remove_metadata() != SCHEMA:
                raise RuntimeError(f"Unsupported K-line archive schema: {segment.relative_path}")
            for batch in file.iter_batches(batch_size=4096, columns=["timestamp", "finalized"]):
                for timestamp, finalized in zip(batch.column(0).to_pylist(), batch.column(1).to_pylist()):
                    yield int(timestamp), bool(finalized)
        finally:
            file.close()

    def _cold_coverage(self, session, segments, hot_bounds):
        first = min(segment.first_timestamp for segment in segments)
        last = max(segment.last_timestamp for segment in segments)
        hot_query = select(Kline.timestamp).where(
            Kline.symbol == segments[0].symbol, Kline.timeframe == segments[0].timeframe,
            Kline.finalized.is_(True), Kline.timestamp >= first, Kline.timestamp <= last,
        )
        if len(segments) == 1 and segments[0].row_count == segments[0].finalized_count:
            hot_overlap = bool(hot_bounds and hot_bounds[0] <= last and hot_bounds[1] >= first)
            if not hot_overlap or session.scalar(hot_query.limit(1)) is None:
                # Immutable manifests were committed only after full round-trip
                # verification. Coverage queries do not repeat payload integrity scans.
                self._segment_path(segments[0])
                return segments[0].finalized_count, first, last

        # Corrections can overlap arbitrarily many segments. Stage only the two
        # visibility columns in connection-local temporary storage: opening one
        # Parquet file at a time avoids fan-in multiplying buffers and handles.
        # Nothing is committed to the application's durable schema or cache.
        coverage = Table("kline_health_coverage", MetaData(),
                         Column("timestamp", BigInteger, primary_key=True), Column("finalized", Boolean, nullable=False),
                         prefixes=["TEMPORARY"])
        connection = session.connection()
        coverage.create(connection)
        try:
            insert = sqlite_insert if connection.dialect.name == "sqlite" else postgres_insert
            statement = insert(coverage)
            statement = statement.on_conflict_do_update(index_elements=[coverage.c.timestamp], set_={"finalized": statement.excluded.finalized})
            for segment in sorted(segments, key=lambda item: (item.archived_at, item.id)):
                stream, batch = self._coverage_flags(segment), []
                try:
                    for timestamp, finalized in stream:
                        batch.append({"timestamp": timestamp, "finalized": finalized})
                        if len(batch) == 4096:
                            session.execute(statement, batch)
                            batch = []
                    if batch:
                        session.execute(statement, batch)
                finally:
                    stream.close()
            # Finalized hot rows are already counted by the SQL aggregate.
            if hot_bounds:
                session.execute(delete(coverage).where(coverage.c.timestamp.in_(hot_query)))
            row = session.execute(select(func.count(), func.min(coverage.c.timestamp), func.max(coverage.c.timestamp))
                                  .where(coverage.c.finalized.is_(True))).one()
            return int(row[0]), row[1], row[2]
        finally:
            coverage.drop(connection)

    def coverage_summary(self, session) -> list[dict]:
        """Exact hot/cold counts without materializing historical OHLCV rows.

        The caller owns a consistent DB read snapshot. Disjoint, fully confirmed
        segments use manifests; only overlapping/mixed segments stream flags.
        """
        summaries = {
            (row[0], row[1]): dict(symbol=row[0], timeframe=row[1], count=int(row[2]), first=row[3], last=row[4])
            for row in session.execute(select(
                Kline.symbol, Kline.timeframe, func.count(), func.min(Kline.timestamp), func.max(Kline.timestamp),
            ).where(Kline.finalized.is_(True)).group_by(Kline.symbol, Kline.timeframe))
        }
        hot_bounds = {scope: (item["first"], item["last"]) for scope, item in summaries.items()}

        def add_component(scope, component):
            if not any(segment.finalized_count for segment in component):
                return
            count, first, last = self._cold_coverage(session, component, hot_bounds.get(scope))
            if not count:
                return
            item = summaries.setdefault(scope, dict(symbol=scope[0], timeframe=scope[1], count=0, first=first, last=last))
            item["count"] += count
            item["first"], item["last"] = min(item["first"], first), max(item["last"], last)

        query = select(KlineArchiveSegment).order_by(
            KlineArchiveSegment.symbol, KlineArchiveSegment.timeframe, KlineArchiveSegment.first_timestamp,
        ).execution_options(yield_per=128)
        segments = session.scalars(query)
        try:
            for scope, group in groupby(segments, key=lambda row: (row.symbol, row.timeframe)):
                component, right = [], None
                for segment in group:
                    if right is not None and segment.first_timestamp > right:
                        add_component(scope, component)
                        component = []
                    component.append(segment)
                    right = segment.last_timestamp if len(component) == 1 else max(right, segment.last_timestamp)
                if component:
                    add_component(scope, component)
        finally:
            segments.close()
        return list(summaries.values())

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
