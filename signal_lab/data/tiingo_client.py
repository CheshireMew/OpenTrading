from __future__ import annotations

from datetime import date
from typing import Any

from signal_lab.data.http import HttpTransport, UrllibJsonTransport


class TiingoDailyClient:
    """Own the Tiingo daily-price request contract."""

    base_url = "https://api.tiingo.com/tiingo/daily"

    def __init__(self, token: str, transport: HttpTransport | None = None) -> None:
        if not token:
            raise ValueError("TIINGO_API_TOKEN is required")
        self.token = token
        self.transport = transport or UrllibJsonTransport()

    def fetch(self, symbol: str, start: date, end: date) -> Any:
        return self.transport.get_json(
            f"{self.base_url}/{symbol}/prices",
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "resampleFreq": "daily",
                "format": "json",
            },
            {"Authorization": f"Token {self.token}"},
        )
