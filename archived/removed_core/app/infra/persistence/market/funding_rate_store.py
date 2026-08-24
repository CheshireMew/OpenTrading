from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import FundingRate


class FundingRateStore:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def save_many(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0

        with self.database_runtime.session_scope() as session:
            dialect_name = session.bind.dialect.name

            if dialect_name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(FundingRate).values(rows)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["exchange", "market_type", "symbol", "funding_time"]
                )
                result = session.execute(stmt)
                return result.rowcount or 0

            if dialect_name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                stmt = sqlite_insert(FundingRate).values(rows)
                stmt = stmt.on_conflict_do_nothing()
                result = session.execute(stmt)
                return result.rowcount or 0

            inserted = 0
            for row in rows:
                exists = (
                    session.query(FundingRate.id)
                    .filter_by(
                        exchange=row["exchange"],
                        market_type=row["market_type"],
                        symbol=row["symbol"],
                        funding_time=row["funding_time"],
                    )
                    .first()
                )
                if exists:
                    continue
                session.add(FundingRate(**row))
                inserted += 1
            return inserted

    def list_history(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            query = session.query(FundingRate).filter_by(
                exchange=exchange,
                market_type=market_type,
            )
            if symbol:
                query = query.filter(FundingRate.symbol == symbol)
            if start_date:
                query = query.filter(FundingRate.funding_time >= start_date)
            if end_date:
                query = query.filter(FundingRate.funding_time <= end_date)
            query = query.order_by(FundingRate.funding_time.asc())
            if limit:
                query = query.limit(limit)
            rows = query.all()
            return [self._serialize(row) for row in rows]

    def latest(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
    ) -> dict[str, Any] | None:
        with self.database_runtime.session_scope() as session:
            row = (
                session.query(FundingRate)
                .filter_by(exchange=exchange, market_type=market_type, symbol=symbol)
                .order_by(desc(FundingRate.funding_time))
                .first()
            )
            return self._serialize(row) if row else None

    def count(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
    ) -> int:
        with self.database_runtime.session_scope() as session:
            return (
                session.query(FundingRate)
                .filter_by(exchange=exchange, market_type=market_type, symbol=symbol)
                .count()
            )

    def _serialize(self, row: FundingRate) -> dict[str, Any]:
        return {
            "exchange": row.exchange,
            "market_type": row.market_type,
            "symbol": row.symbol,
            "funding_time": row.funding_time,
            "funding_rate": row.funding_rate,
            "mark_price": row.mark_price,
        }
