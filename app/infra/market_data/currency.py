"""Public currency-rate acquisition; display and fallback decisions stay in services."""
import httpx

from config import settings


class CurrencyRatesClient:
    def fetch(self):
        with httpx.Client(timeout=settings.CURRENCY_RATES_TIMEOUT) as client:
            response = client.get(settings.CURRENCY_RATES_URL)
        response.raise_for_status()
        return response.json()
