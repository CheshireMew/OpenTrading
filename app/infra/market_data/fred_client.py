from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any

from app.infra.market_data.http import HttpTransport, HttpxJsonTransport


class FredObservationClient:
    """Own the HTTP and wire-format details for FRED observation series."""

    api_url = "https://api.stlouisfed.org/fred/series/observations"
    csv_url = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def __init__(
        self,
        api_key: str = "",
        transport: HttpTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.transport = transport or HttpxJsonTransport()

    def fetch_latest(
        self,
        series_id: str,
        start: date,
        end: date,
    ) -> tuple[dict[str, Any], str]:
        if self.api_key:
            payload = self.transport.get_json(
                self.api_url,
                {
                    "series_id": series_id,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "observation_start": start.isoformat(),
                    "observation_end": end.isoformat(),
                    "limit": "100000",
                },
                {},
            )
            return self._observations_payload(payload, series_id), "series_observations_api"

        text = self.transport.get_bytes(
            self.csv_url,
            {"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()},
            {},
        ).decode("utf-8-sig")
        observations = [
            {
                "date": row.get("DATE") or row.get("observation_date"),
                "value": row.get(series_id),
            }
            for row in csv.DictReader(StringIO(text))
        ]
        return {
            "observations": observations,
            "count": len(observations),
            "source": "fredgraph.csv",
        }, "fredgraph_csv"

    def fetch_all_vintages(self, series_id: str, start: date, end: date) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("FRED_API_KEY is required")
        base_params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
            "realtime_start": "1776-07-04",
            "realtime_end": "9999-12-31",
            "output_type": "1",
            "limit": "100000",
        }
        offset = 0
        observations: list[Any] = []
        metadata: dict[str, Any] | None = None
        while True:
            payload = self.transport.get_json(
                self.api_url,
                {**base_params, "offset": str(offset)},
                {},
            )
            validated = self._observations_payload(payload, series_id)
            metadata = metadata or {
                key: value for key, value in validated.items() if key != "observations"
            }
            page = validated["observations"]
            observations.extend(page)
            total = int(validated.get("count", len(observations)))
            if not page or len(observations) >= total:
                break
            offset += len(page)
        return {**(metadata or {}), "observations": observations, "count": len(observations)}

    @staticmethod
    def _observations_payload(payload: Any, series_id: str) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
            raise ValueError(f"FRED response for {series_id} has no observations list")
        return payload
