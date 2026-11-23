from __future__ import annotations

from typing import Any

from signal_lab.storage import SignalLabDatabase
from signal_lab.storage.macro_repository import IndicatorRepository
from signal_lab.storage.price_repository import PriceRepository
from signal_lab.storage.projections import DatabaseProjection


class WorkbenchView:
    """Read the overview, readiness, and canonical database inventory."""

    def __init__(
        self,
        database: SignalLabDatabase,
    ) -> None:
        self._database = database
        self._projection = DatabaseProjection(database)
        self._prices = PriceRepository(database)
        self._indicators = IndicatorRepository(database)

    def database_status(self) -> dict[str, Any]:
        with self._database.connect() as connection:
            connection.execute("BEGIN")
            summary = self._projection.summary(connection)
            return {
                "schema_version": "signal-lab.database.v1",
                "database_schema_version": summary["schema_version"],
                "path": summary["path"],
                "size_bytes": summary["size_bytes"],
                "counts": summary["counts"],
                "market": [
                    _market_summary(item)
                    for item in self._prices.price_inventory(connection)
                ],
                "price_options": [
                    _market_summary(item)
                    for item in self._prices.daily_explorer_inventory(connection)
                ],
                "macro": [
                    _macro_summary(item)
                    for item in self._indicators.indicator_inventory(connection)
                ],
            }


def _market_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "candle_count": payload["row_count"],
        "first_opened_at": payload["start_at"],
        "last_opened_at": payload["end_at"],
    }


def _macro_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "observation_count": payload["row_count"],
        "first_observed_at": payload["start_at"],
        "last_observed_at": payload["end_at"],
    }
