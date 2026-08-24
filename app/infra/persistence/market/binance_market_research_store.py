from __future__ import annotations

from typing import Any

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import BinanceMarketResearchSeries
from utils.time import utc_now_naive


class BinanceMarketResearchStore:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def save_items(
        self,
        *,
        market: str,
        series: str,
        symbol: str,
        items: list[dict[str, Any]],
        period: str = "",
        contract_type: str = "",
        timestamp_key: str = "timestamp",
        item_key_key: str | None = None,
    ) -> int:
        rows = [
            {
                "market": self._market_key(market),
                "series": series,
                "symbol": self._symbol_key(symbol),
                "period": self._optional_key(period),
                "contract_type": self._optional_key(contract_type),
                "item_key": str(item[item_key_key or timestamp_key]),
                "timestamp": int(item[timestamp_key]),
                "payload": item,
                "created_at": utc_now_naive(),
            }
            for item in items
            if item.get(timestamp_key) is not None and item.get(item_key_key or timestamp_key) is not None
        ]
        if not rows:
            return 0

        with self.database_runtime.session_scope() as session:
            dialect_name = session.bind.dialect.name
            conflict_columns = ["market", "series", "symbol", "period", "contract_type", "item_key"]

            if dialect_name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(BinanceMarketResearchSeries).values(rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=conflict_columns,
                    set_={"payload": stmt.excluded.payload},
                )
                result = session.execute(stmt)
                return result.rowcount or 0

            if dialect_name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                stmt = sqlite_insert(BinanceMarketResearchSeries).values(rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=conflict_columns,
                    set_={"payload": stmt.excluded.payload},
                )
                result = session.execute(stmt)
                return result.rowcount or 0

            changed = 0
            for row in rows:
                existing = (
                    session.query(BinanceMarketResearchSeries)
                    .filter_by(
                        market=row["market"],
                        series=row["series"],
                        symbol=row["symbol"],
                        period=row["period"],
                        contract_type=row["contract_type"],
                        item_key=row["item_key"],
                    )
                    .first()
                )
                if existing:
                    existing.payload = row["payload"]
                else:
                    session.add(BinanceMarketResearchSeries(**row))
                changed += 1
            return changed

    def list_items(
        self,
        *,
        market: str,
        series: str,
        symbol: str,
        period: str = "",
        contract_type: str = "",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            query = session.query(BinanceMarketResearchSeries).filter_by(
                market=self._market_key(market),
                series=series,
                symbol=self._symbol_key(symbol),
                period=self._optional_key(period),
                contract_type=self._optional_key(contract_type),
            )
            if start_time is not None:
                query = query.filter(BinanceMarketResearchSeries.timestamp >= start_time)
            if end_time is not None:
                query = query.filter(BinanceMarketResearchSeries.timestamp <= end_time)
            query = query.order_by(BinanceMarketResearchSeries.timestamp.desc())
            if limit:
                query = query.limit(limit)
            rows = query.all()
            return [row.payload for row in reversed(rows)]

    @staticmethod
    def _market_key(market: str) -> str:
        return market.strip().lower()

    @staticmethod
    def _symbol_key(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _optional_key(value: str | None) -> str:
        return (value or "").strip()
