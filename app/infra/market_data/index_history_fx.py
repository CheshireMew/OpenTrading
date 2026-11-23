from __future__ import annotations

from datetime import datetime

import requests

from config import settings


class IndexCurrencyHistoryProvider:
    """Historical currency conversion for index benchmark prices."""

    def fetch_usd_fx_rates(
        self, currency: str, start_dt: datetime, end_dt: datetime,
    ) -> dict[str, float]:
        response = requests.get(
            f"https://api.frankfurter.app/{start_dt.strftime('%Y-%m-%d')}..{end_dt.strftime('%Y-%m-%d')}",
            params={"from": currency, "to": "USD"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        rates = response.json().get("rates") or {}
        return {
            date_text: float((values or {}).get("USD"))
            for date_text, values in rates.items()
            if (values or {}).get("USD") is not None
        }
