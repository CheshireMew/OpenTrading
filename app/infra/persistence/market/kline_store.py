from __future__ import annotations

import json
import time
from functools import lru_cache
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, select
from typing import List

from config import settings
from config.settings import DATA_DIR
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import Kline
from app.domain.market.candles import candle_end_ms, current_candle_open_ms
from app.domain.market.constants import timeframe_to_milliseconds
from app.domain.market.resampling import aggregate_complete, synthesis_sources
from app.infra.persistence.market.kline_archive import KlineArchive, record_bytes
from utils.logger import logger


@lru_cache(maxsize=1)
def _load_early_btc_history() -> List[List]:
    file_path = DATA_DIR / "btc_history_early.json"
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"加载早期 BTC 历史代理数据: {len(data)} 条 (含合成区间，内存缓存)")
            return data
    return []


class KlineStore:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime
        self.archive = KlineArchive(database_runtime)

    def get_before(self, symbol: str, timeframe: str, end_ts: int, limit: int) -> list[list[float]]:
        if limit <= 0:
            return []
        with self.database_runtime.session_scope() as session:
            direct = self._exact(session, symbol, timeframe, None, end_ts - 1, limit=limit)
            merged = {int(row[0]): row for row in direct}
            duration = timeframe_to_milliseconds(timeframe)
            for source in synthesis_sources(symbol, timeframe):
                ratio = duration // timeframe_to_milliseconds(source)
                size = min(50_000, max(1000, (limit + 2) * ratio))
                before, carry = end_ts - 1, []
                while True:
                    rows = self._exact(session, symbol, source, None, before, limit=size)
                    if not rows:
                        break
                    combined = rows + carry
                    for row in aggregate_complete(combined, source, timeframe):
                        if int(row[0]) < end_ts:
                            merged.setdefault(int(row[0]), row)
                    first = int(rows[0][0])
                    bucket = current_candle_open_ms(first, timeframe)
                    carry = [r for r in combined if current_candle_open_ms(int(r[0]), timeframe) == bucket]
                    if len(rows) < size or (len(merged) >= limit and bucket < sorted(merged)[-limit]):
                        break
                    before = first - 1
            return [merged[t] for t in sorted(merged)[-limit:]]

    def get_range(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list[list[float]]:
        with self.database_runtime.session_scope() as session:
            cached_klines = self._exact(session, symbol, timeframe, start_ts, end_ts)

            if symbol == "BTC/USDT" and timeframe == "1d" and start_ts < settings.BTC_EARLY_HISTORY_CUTOFF_TS:
                early_in_db = (
                    session.query(Kline)
                    .filter(
                        Kline.symbol == symbol,
                        Kline.timeframe == timeframe,
                        Kline.timestamp < settings.BTC_EARLY_HISTORY_CUTOFF_TS,
                        Kline.finalized.is_(True),
                    )
                    .count()
                )

                early_in_archive = self.archive.read(session, symbol, timeframe, None,
                                                       settings.BTC_EARLY_HISTORY_CUTOFF_TS - 1, limit=1)
                if early_in_db == 0 and not early_in_archive:
                    early_history = _load_early_btc_history()
                    if early_history:
                        self._save_with_session(session, symbol, timeframe, early_history)
                        logger.info(f"早期 BTC 历史代理数据已写入 DB: {len(early_history)} 条 (含合成区间)")
                        cached_klines = self._exact(session, symbol, timeframe, start_ts, end_ts)
            return self._fill_from_smaller(session, symbol, timeframe, start_ts, end_ts, cached_klines)

    def _exact(self, session, symbol, timeframe, start, end, *, limit=None):
        query = session.query(Kline).filter(Kline.symbol == symbol, Kline.timeframe == timeframe,
                                           Kline.timestamp <= end, Kline.finalized.is_(True))
        if start is not None:
            query = query.filter(Kline.timestamp >= start)
        if limit:
            query = query.order_by(Kline.timestamp.desc()).limit(limit)
        # Read hot rows before archive references: an atomic archival commit
        # between the two reads can create overlap, but cannot create a gap.
        hot = [row.to_list() for row in query.all()]
        cold_start = max(start or 0, min(int(r[0]) for r in hot)) if limit and len(hot) == limit else start
        cold = self.archive.read(session, symbol, timeframe, cold_start, end, limit=limit)
        merged = {int(row[0]): list(row[:6]) for row in cold}
        merged.update({int(row[0]): row for row in hot})
        rows = [merged[t] for t in sorted(merged)]
        return rows[-limit:] if limit else rows

    def _fill_from_smaller(self, session, symbol, timeframe, start, end, direct):
        sources = synthesis_sources(symbol, timeframe)
        if not sources or end < start:
            return direct
        first = current_candle_open_ms(start, timeframe)
        if first < start:
            first = candle_end_ms(first, timeframe)
        now = int(time.time() * 1000)
        last = current_candle_open_ms(min(end, now), timeframe)
        if candle_end_ms(last, timeframe) > now:
            last = current_candle_open_ms(last - 1, timeframe)
        if first > last:
            return direct
        merged = {int(row[0]): row for row in direct}
        missing = []
        timestamp = first
        while timestamp <= last:
            if timestamp not in merged:
                missing.append(timestamp)
            timestamp = candle_end_ms(timestamp, timeframe)
        for source in sources:
            if not missing:
                break
            # Only hydrate gaps, in bounded windows. Never re-read years of
            # already present higher-timeframe candles to compose a few bars.
            ranges = []
            for timestamp in missing:
                right = candle_end_ms(timestamp, timeframe)
                if ranges and timestamp == ranges[-1][1] and timestamp - ranges[-1][0] < 30 * 86400000:
                    ranges[-1] = (ranges[-1][0], right)
                else:
                    ranges.append((timestamp, right))
            for left, right in ranges:
                rows = self._exact(session, symbol, source, left, right - 1)
                for row in aggregate_complete(rows, source, timeframe):
                    merged.setdefault(int(row[0]), row)
            missing = [t for t in missing if t not in merged]
        return [merged[t] for t in sorted(merged) if start <= t <= end]

    def save(self, symbol: str, timeframe: str, klines: list[list[float]]) -> None:
        if not klines:
            return
        with self.database_runtime.session_scope() as session:
            by_time = {int(row[0]): row for row in klines}
            start, end = min(by_time), max(by_time)
            hot_times = set(session.scalars(select(Kline.timestamp).where(
                Kline.symbol == symbol, Kline.timeframe == timeframe,
                Kline.timestamp >= start, Kline.timestamp <= end)))
            cold = {int(row[0]): row for row in self.archive.read(
                session, symbol, timeframe, start, end, finalized_only=False)}
            synthesized = {int(row[0]): row for row in self._fill_from_smaller(
                session, symbol, timeframe, start, end, [])}
            now = int(time.time() * 1000)
            pending = []
            for timestamp, row in sorted(by_time.items()):
                finalized = candle_end_ms(timestamp, timeframe) <= now
                previous = cold.get(timestamp)
                if previous is not None and timestamp not in hot_times:
                    if previous[6] and not finalized:
                        continue
                    if record_bytes((*row, finalized)) == record_bytes(previous):
                        continue
                # Avoid a second physical copy only when a complete, confirmed
                # lower series reproduces every value exactly. Originals with
                # different rounding/volume remain stored without alteration.
                if timestamp not in hot_times and finalized and synthesized.get(timestamp) == row:
                    continue
                pending.append(row)
            self._save_with_session(session, symbol, timeframe, pending)

    def _save_with_session(self, session, symbol: str, timeframe: str, klines: list[list[float]]) -> None:
        if not klines:
            return
        try:
            dialect_name = session.bind.dialect.name
            batch_size = max(int(settings.KLINE_UPSERT_BATCH_SIZE), 1)
            observed_at = int(time.time() * 1000)

            def values_for(batch):
                return [
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "timestamp": k[0],
                        "open": k[1],
                        "high": k[2],
                        "low": k[3],
                        "close": k[4],
                        "volume": k[5],
                        "finalized": candle_end_ms(int(k[0]), timeframe) <= observed_at,
                    }
                    for k in batch
                ]

            if dialect_name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                for start in range(0, len(klines), batch_size):
                    stmt = pg_insert(Kline).values(
                        values_for(klines[start:start + batch_size])
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["symbol", "timeframe", "timestamp"],
                        set_={
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "volume": stmt.excluded.volume,
                            "finalized": stmt.excluded.finalized,
                        },
                        where=((~Kline.finalized | stmt.excluded.finalized) & or_(
                            *(getattr(Kline, field).is_distinct_from(getattr(stmt.excluded, field))
                              for field in ("open", "high", "low", "close", "volume", "finalized")))),
                    )
                    session.execute(stmt)
            elif dialect_name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                for start in range(0, len(klines), batch_size):
                    stmt = sqlite_insert(Kline).values(
                        values_for(klines[start:start + batch_size])
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["symbol", "timeframe", "timestamp"],
                        set_={
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "volume": stmt.excluded.volume,
                            "finalized": stmt.excluded.finalized,
                        },
                        where=((~Kline.finalized | stmt.excluded.finalized) & or_(
                            *(getattr(Kline, field).is_distinct_from(getattr(stmt.excluded, field))
                              for field in ("open", "high", "low", "close", "volume", "finalized")))),
                    )
                    session.execute(stmt)
            else:
                from sqlalchemy.exc import IntegrityError as SAIntegrityError

                for start in range(0, len(klines), batch_size):
                    values = values_for(klines[start:start + batch_size])
                    for value in values:
                        try:
                            session.execute(Kline.__table__.insert().values(**value))
                            session.flush()
                        except SAIntegrityError:
                            session.rollback()
        except SQLAlchemyError as exc:
            session.rollback()
            logger.error(
                "保存 K 线缓存失败: "
                f"symbol={symbol} timeframe={timeframe} rows={len(klines)} reason={self._safe_db_error(exc)}"
            )
            raise
        except Exception as exc:
            session.rollback()
            logger.error(
                "保存 K 线缓存失败: "
                f"symbol={symbol} timeframe={timeframe} rows={len(klines)} reason={self._safe_db_error(exc)}"
            )
            raise

    @staticmethod
    def _safe_db_error(exc: Exception) -> str:
        original = getattr(exc, "orig", None)
        message = str(original or exc).splitlines()[0]
        if len(message) > 240:
            return f"{message[:240]}..."
        return message
