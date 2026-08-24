from __future__ import annotations

from datetime import datetime, timezone

import requests

from app.domain.market.sentiment import SentimentRecord


class SentimentApiClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url

    def fetch_history(self) -> list[SentimentRecord]:
        response = requests.get(f"{self.api_url}?limit=0", timeout=30)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", [])
        return [
            SentimentRecord(
                date=datetime.fromtimestamp(int(item["timestamp"]), tz=timezone.utc),
                value=int(item["value"]),
                classification=item["value_classification"],
                timestamp=int(item["timestamp"]),
            )
            for item in rows
        ]
