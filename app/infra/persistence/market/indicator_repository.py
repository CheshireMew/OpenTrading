from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import MarketIndicatorData, MarketIndicatorMeta


class MarketIndicatorRepository:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def list_active_meta(self, category: str | None = None) -> list[dict[str, Any]]:
        with self.database_runtime.session_scope() as session:
            query = session.query(MarketIndicatorMeta).filter(MarketIndicatorMeta.is_active == 1)
            if category:
                query = query.filter(MarketIndicatorMeta.category == category)
            rows = query.order_by(MarketIndicatorMeta.category.asc(), MarketIndicatorMeta.name.asc()).all()
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "category": row.category,
                    "unit": row.unit,
                    "frequency": row.frequency,
                    "description": row.description,
                }
                for row in rows
            ]

    def get_history_points(
        self,
        indicator_ids: list[str],
        *,
        start_date: datetime | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not indicator_ids:
            return {}

        with self.database_runtime.session_scope() as session:
            query = session.query(MarketIndicatorData).filter(MarketIndicatorData.indicator_id.in_(indicator_ids))
            if start_date:
                query = query.filter(MarketIndicatorData.timestamp >= start_date)
            rows = query.order_by(
                MarketIndicatorData.indicator_id.asc(),
                MarketIndicatorData.timestamp.asc(),
            ).all()
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                grouped[row.indicator_id].append(
                    {
                        "date": row.timestamp.isoformat(),
                        "timestamp": row.timestamp,
                        "value": row.value,
                    }
                )
            return grouped

    def get_latest_timestamps(self, indicator_ids: list[str]) -> dict[str, datetime]:
        if not indicator_ids:
            return {}
        with self.database_runtime.session_scope() as session:
            rows = (
                session.query(
                    MarketIndicatorData.indicator_id,
                    func.max(MarketIndicatorData.timestamp),
                )
                .filter(MarketIndicatorData.indicator_id.in_(indicator_ids))
                .group_by(MarketIndicatorData.indicator_id)
                .all()
            )
            return {
                str(indicator_id): latest
                for indicator_id, latest in rows
                if latest is not None
            }

    def upsert_points(self, data_points: list[dict[str, Any]], meta_catalog: dict[str, tuple[str, str, str]]) -> None:
        if not data_points:
            return

        deduplicated = {
            (str(point["indicator_id"]), point["timestamp"]): {
                "indicator_id": str(point["indicator_id"]),
                "timestamp": point["timestamp"],
                "value": float(point["value"]),
            }
            for point in data_points
        }
        rows = list(deduplicated.values())
        indicator_ids = sorted({row["indicator_id"] for row in rows})

        with self.database_runtime.session_scope() as session:
            existing_meta = {
                item.id: item
                for item in session.query(MarketIndicatorMeta)
                .filter(MarketIndicatorMeta.id.in_(indicator_ids))
                .all()
            }
            missing_meta: list[MarketIndicatorMeta] = []
            for indicator_id in indicator_ids:
                display_name, category, unit = meta_catalog.get(
                    indicator_id,
                    (indicator_id.replace("_", " ").title(), "General", ""),
                )
                meta = existing_meta.get(indicator_id)
                if meta is None:
                    missing_meta.append(
                        MarketIndicatorMeta(
                            id=indicator_id,
                            name=display_name,
                            category=category,
                            unit=unit,
                        )
                    )
                elif meta.category == "General":
                    meta.category = category
                    meta.name = display_name
                    meta.unit = unit
            if missing_meta:
                session.add_all(missing_meta)
            session.flush()

            dialect_name = session.get_bind().dialect.name
            chunk_size = 250
            for offset in range(0, len(rows), chunk_size):
                chunk = rows[offset : offset + chunk_size]
                if dialect_name == "postgresql":
                    statement = postgresql_insert(MarketIndicatorData).values(chunk)
                    session.execute(
                        statement.on_conflict_do_update(
                            index_elements=["indicator_id", "timestamp"],
                            set_={"value": statement.excluded.value},
                        )
                    )
                elif dialect_name == "sqlite":
                    statement = sqlite_insert(MarketIndicatorData).values(chunk)
                    session.execute(
                        statement.on_conflict_do_update(
                            index_elements=["indicator_id", "timestamp"],
                            set_={"value": statement.excluded.value},
                        )
                    )
                else:
                    self._generic_upsert_chunk(session, chunk)

    @staticmethod
    def _generic_upsert_chunk(session, rows: list[dict[str, Any]]) -> None:
        keys = [(row["indicator_id"], row["timestamp"]) for row in rows]
        existing = {
            (item.indicator_id, item.timestamp): item
            for item in session.query(MarketIndicatorData)
            .filter(tuple_(MarketIndicatorData.indicator_id, MarketIndicatorData.timestamp).in_(keys))
            .all()
        }
        inserts: list[MarketIndicatorData] = []
        for row in rows:
            key = (row["indicator_id"], row["timestamp"])
            current = existing.get(key)
            if current is None:
                inserts.append(MarketIndicatorData(**row))
            else:
                current.value = row["value"]
        if inserts:
            session.add_all(inserts)
