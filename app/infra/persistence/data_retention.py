"""
数据保留策略 - 旧 Kline 经无损归档、逐值校验后移出在线表
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text

from app.infra.db import DatabaseRuntime
from app.infra.db.schema import Kline, KlineArchiveSegment
from app.infra.persistence.market.kline_archive import KlineArchive, FIELDS
from config import settings
from utils.logger import logger

# 短周期时间框架，日线/周线/月线不清理
SHORT_TIMEFRAMES = ("1m", "5m", "15m", "15min", "30m", "1h", "4h")


def archive_batch(database_runtime: DatabaseRuntime, *, cutoff_ts: int, batch_size: int) -> int:
    """Commit one bounded move; failure leaves all source rows intact and retryable."""
    archive = KlineArchive(database_runtime)
    with database_runtime.session_scope() as session:
        postgres = database_runtime.engine.dialect.name == "postgresql"
        if postgres:
            if not session.scalar(text("SELECT pg_try_advisory_xact_lock(485374620219)")):
                raise RuntimeError("Another K-line archival transaction is running; retry later")
        else:
            session.execute(text("BEGIN IMMEDIATE"))
        scope = session.execute(select(Kline.symbol, Kline.timeframe).where(
            Kline.timeframe.in_(SHORT_TIMEFRAMES), Kline.timestamp < cutoff_ts,
        ).order_by(Kline.timeframe, Kline.timestamp).limit(1)).first()
        if scope is None:
            return 0
        symbol, timeframe = scope
        statement = select(*(getattr(Kline, field) for field in FIELDS)).where(
            Kline.symbol == symbol, Kline.timeframe == timeframe, Kline.timestamp < cutoff_ts,
        ).order_by(Kline.timestamp).limit(max(1, min(batch_size, 50_000)))
        if postgres:
            statement = statement.with_for_update()
        rows = [tuple(row) for row in session.execute(statement)]
        segment = archive.write_verified(symbol, timeframe, rows)
        previous = session.get(KlineArchiveSegment, segment.id)
        if previous is None:
            session.add(segment)
        else:
            # An interrupted/repeated batch reuses its content-addressed file.
            previous.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.flush()
        # Locks cover the original values through file verification and commit.
        # The file and its manifest exist before any source row is removed.
        result = session.execute(delete(Kline).where(
            Kline.symbol == symbol, Kline.timeframe == timeframe,
            Kline.timestamp.in_([row[0] for row in rows]),
        ))
        if result.rowcount != len(rows):
            raise RuntimeError("K-line archive source changed during verification")
        return len(rows)


def cleanup_old_data(database_runtime: DatabaseRuntime) -> int:
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=settings.KLINE_RETENTION_DAYS)).timestamp() * 1000)
    archived = 0
    while moved := archive_batch(database_runtime, cutoff_ts=cutoff_ts,
                                 batch_size=max(int(settings.KLINE_RETENTION_BATCH_SIZE), 1)):
        archived += moved
    logger.info(f"[retention] Losslessly archived {archived} short-tf klines older than {settings.KLINE_RETENTION_DAYS}d")
    return archived
