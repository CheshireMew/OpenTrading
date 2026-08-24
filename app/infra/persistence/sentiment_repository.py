from __future__ import annotations

from datetime import datetime

from app.domain.market.sentiment import SentimentRecord
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import Sentiment


class SentimentRepository:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def get_latest_date(self) -> datetime | None:
        with self.database_runtime.session_scope() as session:
            latest = session.query(Sentiment).order_by(Sentiment.date.desc()).first()
            return latest.date if latest else None

    def save_missing(self, records: list[SentimentRecord]) -> int:
        if not records:
            return 0
        with self.database_runtime.session_scope() as session:
            existing_dates = {row[0].date() for row in session.query(Sentiment.date).all()}
            new_records = [
                Sentiment(
                    date=record.date,
                    value=record.value,
                    classification=record.classification,
                    timestamp=record.timestamp,
                )
                for record in records
                if record.date.date() not in existing_dates
            ]
            if not new_records:
                return 0
            session.bulk_save_objects(new_records)
            return len(new_records)

    def list_history(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, int]:
        with self.database_runtime.session_scope() as session:
            query = session.query(Sentiment).order_by(Sentiment.date.asc())
            if start_date:
                query = query.filter(Sentiment.date >= start_date)
            if end_date:
                query = query.filter(Sentiment.date <= end_date)
            return {row.date.strftime("%Y-%m-%d"): row.value for row in query.all()}

    def get_latest_index(self) -> dict[str, int | str] | None:
        with self.database_runtime.session_scope() as session:
            latest = session.query(Sentiment).order_by(Sentiment.date.desc()).first()
            if not latest:
                return None
            return {
                "value": latest.value,
                "value_classification": latest.classification,
                "timestamp": latest.timestamp,
            }
