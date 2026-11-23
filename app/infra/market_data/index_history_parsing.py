from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Iterable
from typing import Any


def redact_exception_message(exc: Exception, secrets: Iterable[str | None] = ()) -> str:
    message = str(exc)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    return message


class IndexHistoryParsing:
    def parse_eastmoney_row(self, row: str) -> list[float]:
        date_text, open_text, close_text, high_text, low_text, volume_text, *_rest = row.split(",")
        return [
            self.to_ms(self.parse_date(date_text)),
            float(open_text),
            float(high_text),
            float(low_text),
            float(close_text),
            float(volume_text),
        ]

    def parse_sohu_row(self, row: list[str]) -> list[float]:
        return [
            self.to_ms(self.parse_date(row[0])),
            float(row[1]),
            float(row[6]),
            float(row[5]),
            float(row[2]),
            float(row[7]),
        ]

    def frame_to_ohlcv(
        self,
        *,
        frame,
        start_dt: datetime,
        end_dt: datetime,
        volume_field: str,
    ) -> list[list[float]]:
        if frame is None or frame.empty:
            return []

        data: list[list[float]] = []
        for row in frame.to_dict("records"):
            if any(row.get(field) is None for field in ("date", "open", "high", "low", "close")):
                continue
            row_dt = self.normalize_date_value(row["date"])
            if row_dt < start_dt or row_dt > end_dt:
                continue
            data.append([
                self.to_ms(row_dt),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row.get(volume_field) or 0.0),
            ])
        data.sort(key=lambda item: item[0])
        return data

    def parse_date(self, value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    def normalize_date_value(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return self.parse_date(str(value))

    def date_to_ms(self, value: datetime) -> int:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return self.to_ms(value.astimezone(timezone.utc))

    def to_ms(self, value: datetime) -> int:
        return int(value.timestamp() * 1000)
