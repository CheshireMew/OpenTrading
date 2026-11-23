"""Inspect, archive, verify and restore OHLCV without downloading market data.

python -m scripts.market_storage status
python -m scripts.market_storage archive --apply
python -m scripts.market_storage verify
python -m scripts.market_storage restore --apply
python -m scripts.market_storage compact --apply
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

from sqlalchemy import func, select, text

from app.infra.db import build_database_runtime
from app.infra.db.schema import Kline, KlineArchiveSegment
from app.infra.persistence.data_retention import SHORT_TIMEFRAMES, archive_batch
from app.infra.persistence.market.kline_archive import KlineArchive, FIELDS, content_hash, record_bytes
from config import settings


def inventory(runtime, cutoff):
    with runtime.session_scope() as session:
        hot = session.scalar(select(func.count()).select_from(Kline))
        eligible = session.scalar(select(func.count()).select_from(Kline).where(
            Kline.timeframe.in_(SHORT_TIMEFRAMES), Kline.timestamp < cutoff))
        segments = session.scalar(select(func.count()).select_from(KlineArchiveSegment))
        archived = int(session.scalar(select(func.sum(KlineArchiveSegment.row_count))) or 0)
        compressed = int(session.scalar(select(func.sum(KlineArchiveSegment.size_bytes))) or 0)
        size = session.scalar(text("SELECT pg_total_relation_size('klines')")) if runtime.engine.dialect.name == "postgresql" else None
        return dict(hot_rows=hot, eligible_rows=eligible, archive_segments=segments,
                    archived_rows_including_versions=archived, archive_bytes=compressed,
                    hot_relation_bytes=size, archive_root=str(runtime.archive_root))


def verify(runtime):
    archive = KlineArchive(runtime)
    total = count = 0
    with runtime.session_scope() as session:
        for segment in session.scalars(select(KlineArchiveSegment).order_by(KlineArchiveSegment.id)):
            rows = archive.read_segment(segment)
            if (len(rows) != segment.row_count
                    or content_hash(segment.symbol, segment.timeframe, rows) != segment.id
                    or sum(bool(r[6]) for r in rows) != segment.finalized_count
                    or rows[0][0] != segment.first_timestamp or rows[-1][0] != segment.last_timestamp):
                raise RuntimeError(f"Archive verification failed: {segment.relative_path}")
            total += len(rows)
            count += 1
    return dict(verified_segments=count, verified_original_rows=total)


def fingerprints(runtime):
    """Compare all original values before/after moves using bounded month windows."""
    archive = KlineArchive(runtime)
    with runtime.session_scope() as session:
        hot = session.execute(select(Kline.symbol, Kline.timeframe, func.min(Kline.timestamp),
                                     func.max(Kline.timestamp)).group_by(Kline.symbol, Kline.timeframe)).all()
        cold = session.execute(select(KlineArchiveSegment.symbol, KlineArchiveSegment.timeframe,
                                      func.min(KlineArchiveSegment.first_timestamp),
                                      func.max(KlineArchiveSegment.last_timestamp))
                               .group_by(KlineArchiveSegment.symbol, KlineArchiveSegment.timeframe)).all()
        scopes = {}
        for symbol, timeframe, first, last in [*hot, *cold]:
            previous = scopes.get((symbol, timeframe), (first, last))
            scopes[symbol, timeframe] = (min(first, previous[0]), max(last, previous[1]))
        results = []
        for (symbol, timeframe), (first, last) in sorted(scopes.items()):
            digest = sha256(json.dumps([symbol, timeframe], separators=(",", ":")).encode())
            left = first
            count = confirmed = 0
            while left <= last:
                date = datetime.fromtimestamp(left / 1000, timezone.utc)
                next_month = date.replace(year=date.year + (date.month == 12),
                                          month=date.month % 12 + 1, day=1,
                                          hour=0, minute=0, second=0, microsecond=0)
                right = min(last, int(next_month.timestamp() * 1000) - 1)
                hot_rows = session.execute(select(*(getattr(Kline, f) for f in FIELDS)).where(
                    Kline.symbol == symbol, Kline.timeframe == timeframe,
                    Kline.timestamp >= left, Kline.timestamp <= right)).all()
                merged = {int(r[0]): r for r in archive.read(session, symbol, timeframe, left, right,
                                                           finalized_only=False)}
                merged.update({int(r[0]): r for r in hot_rows})
                for timestamp in sorted(merged):
                    row = merged[timestamp]
                    digest.update(record_bytes(row))
                    count += 1
                    confirmed += bool(row[6])
                left = right + 1
            results.append(dict(symbol=symbol, timeframe=timeframe, count=count,
                                finalized_count=confirmed, first=first, last=last,
                                original_values_sha256=digest.hexdigest()))
    return dict(scopes=results, unique_original_rows=sum(s["count"] for s in results))


def restore(runtime):
    """Restore original flags too; existing hot corrections always take precedence."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    archive = KlineArchive(runtime)
    restored = 0
    with runtime.session_scope() as session:
        segments = session.scalars(select(KlineArchiveSegment).order_by(
            KlineArchiveSegment.archived_at.desc(), KlineArchiveSegment.id.desc())).all()
    for segment in segments:
        with runtime.session_scope() as session:
            rows = archive.read_segment(segment)
            for start in range(0, len(rows), 1000):
                values = [dict(symbol=segment.symbol, timeframe=segment.timeframe, timestamp=r[0], open=r[1], high=r[2],
                               low=r[3], close=r[4], volume=r[5], finalized=r[6]) for r in rows[start:start + 1000]]
                insert = pg_insert if runtime.engine.dialect.name == "postgresql" else sqlite_insert
                statement = insert(Kline).values(values).on_conflict_do_nothing(
                    index_elements=["symbol", "timeframe", "timestamp"])
                restored += session.execute(statement).rowcount
    return dict(restored_rows=restored, archive_retained=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "archive", "verify", "fingerprint", "restore", "compact"])
    parser.add_argument("--baseline", type=Path, help="Compare verify against a prior fingerprint JSON")
    parser.add_argument("--apply", action="store_true", help="Apply the requested local database operation")
    parser.add_argument("--days", type=int, default=settings.KLINE_RETENTION_DAYS)
    parser.add_argument("--batch-size", type=int, default=50_000)
    args = parser.parse_args()
    if args.days < 1 or not 1 <= args.batch_size <= 50_000:
        parser.error("days must be positive; batch-size must be 1..50000")
    runtime = build_database_runtime(settings)
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
    try:
        if args.action == "verify":
            result = verify(runtime)
            if args.baseline:
                expected = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
                actual = fingerprints(runtime)
                if expected != actual:
                    raise RuntimeError("Original history differs from baseline; preserve files and restore before proceeding")
                result.update(baseline_matches=True, original_rows=actual["unique_original_rows"])
        elif args.action == "fingerprint":
            result = fingerprints(runtime)
        elif args.action == "status" or not args.apply:
            result = dict(action=args.action, apply=False, **inventory(runtime, cutoff))
        elif args.action == "archive":
            total = 0
            while moved := archive_batch(runtime, cutoff_ts=cutoff, batch_size=args.batch_size):
                total += moved
                print(json.dumps(dict(archived_this_batch=moved, archived_total=total)), flush=True)
            result = dict(archived_total=total, **inventory(runtime, cutoff))
        elif args.action == "restore":
            result = restore(runtime)
        else:
            verified = verify(runtime)
            if runtime.engine.dialect.name != "postgresql":
                raise RuntimeError("compact currently targets PostgreSQL only")
            # Run after archival, when the remaining live table is small. This
            # rewrites it and its indexes and requires a maintenance window.
            with runtime.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text("SET lock_timeout='5s'"))
                connection.execute(text("VACUUM (FULL, ANALYZE) klines"))
            result = dict(**verified, **inventory(runtime, cutoff))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        runtime.dispose()


if __name__ == "__main__":
    main()
