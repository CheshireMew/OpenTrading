"""
数据保留策略 - 定期清理过期的 Kline 数据
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, tuple_

from app.infra.db import DatabaseRuntime
from app.infra.db.schema import Kline
from config import settings
from utils.logger import logger

# 短周期时间框架，日线/周线/月线不清理
SHORT_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h")


def cleanup_old_data(database_runtime: DatabaseRuntime) -> int:
    """按稳定主键顺序分批清理过期数据，并返回实际删除数量。"""
    session = database_runtime.get_session()
    deleted_total = 0
    try:
        cutoff_ts = int(
            (datetime.now(timezone.utc) - timedelta(days=settings.KLINE_RETENTION_DAYS)).timestamp() * 1000
        )
        batch_size = max(int(settings.KLINE_RETENTION_BATCH_SIZE), 1)
        while True:
            keys = list(
                session.execute(
                    select(Kline.symbol, Kline.timeframe, Kline.timestamp)
                    .where(
                        Kline.timeframe.in_(SHORT_TIMEFRAMES),
                        Kline.timestamp < cutoff_ts,
                    )
                    .order_by(Kline.timestamp, Kline.timeframe, Kline.symbol)
                    .limit(batch_size)
                )
            )
            if not keys:
                break
            result = session.execute(
                delete(Kline).where(
                    tuple_(Kline.symbol, Kline.timeframe, Kline.timestamp).in_(keys)
                )
            )
            session.commit()
            deleted_total += int(result.rowcount or 0)
            if len(keys) < batch_size:
                break
        logger.info(
            f"[retention] Deleted {deleted_total} short-tf klines older than "
            f"{settings.KLINE_RETENTION_DAYS}d in batches of {batch_size}"
        )
        return deleted_total
    except Exception as e:
        session.rollback()
        logger.error(f"[retention] Cleanup failed: {e}")
        raise
    finally:
        session.close()
