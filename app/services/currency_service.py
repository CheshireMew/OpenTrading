from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.services.market.symbol_catalog import get_usd_equivalent_symbols
from app.infra.executor import run_external_io
from config import settings
from utils.logger import logger


FALLBACK_RATES_PER_USD: dict[str, float] = {
    "USD": 1.0,
    "CNY": 7.25,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 150.0,
    "HKD": 7.8,
    "SGD": 1.35,
    "AUD": 1.52,
}

DISPLAY_CURRENCY_META: dict[str, dict[str, Any]] = {
    "USD": {"name": "US Dollar", "symbol": "$", "locale": "en-US", "fraction_digits": 2},
    "CNY": {"name": "人民币", "symbol": "¥", "locale": "zh-CN", "fraction_digits": 2},
    "EUR": {"name": "Euro", "symbol": "€", "locale": "de-DE", "fraction_digits": 2},
    "GBP": {"name": "British Pound", "symbol": "£", "locale": "en-GB", "fraction_digits": 2},
    "JPY": {"name": "Japanese Yen", "symbol": "¥", "locale": "ja-JP", "fraction_digits": 0},
    "HKD": {"name": "Hong Kong Dollar", "symbol": "HK$", "locale": "zh-HK", "fraction_digits": 2},
    "SGD": {"name": "Singapore Dollar", "symbol": "S$", "locale": "en-SG", "fraction_digits": 2},
    "AUD": {"name": "Australian Dollar", "symbol": "A$", "locale": "en-AU", "fraction_digits": 2},
}


class CurrencyRateService:
    def __init__(self) -> None:
        self._cache: dict[str, Any] | None = None
        self._expires_at: datetime | None = None
        self._refresh_task = None

    async def get_rates(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if self._cache and self._expires_at and self._expires_at > now:
            return self._cache

        if self._cache is None:
            self._cache = self._build_fallback_payload(now)
            self._expires_at = now + timedelta(seconds=60)

        self._request_refresh()
        return self._cache

    def _request_refresh(self) -> None:
        import asyncio

        if self._refresh_task is not None and not self._refresh_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._refresh_task = loop.create_task(self._refresh_rates())

    async def _refresh_rates(self) -> None:
        now = datetime.now(timezone.utc)
        try:
            payload = await run_external_io(lambda: self._fetch_live_rates(now))
        except Exception as exc:
            logger.warning(f"Currency rate refresh failed, keeping cached rates: {exc}")
            return
        self._cache = payload
        ttl = settings.CURRENCY_RATES_TTL if not payload.get("is_fallback") else 60
        self._expires_at = now + timedelta(seconds=max(ttl, 60))

    def _build_fallback_payload(self, now: datetime) -> dict[str, Any]:
        supported_codes = self._supported_codes()
        return self._build_payload(
            rates={code: FALLBACK_RATES_PER_USD[code] for code in supported_codes},
            updated_at=now,
            source="fallback",
            is_fallback=True,
        )

    def _fetch_live_rates(self, now: datetime) -> dict[str, Any]:
        supported_codes = self._supported_codes()
        fallback = self._build_fallback_payload(now)
        try:
            with httpx.Client(timeout=settings.CURRENCY_RATES_TIMEOUT) as client:
                response = client.get(settings.CURRENCY_RATES_URL)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning(f"Currency rate fetch failed, using fallback rates: {exc}")
            return fallback

        raw_rates = data.get("rates") if isinstance(data, dict) else None
        if not isinstance(raw_rates, dict):
            return fallback

        rates: dict[str, float] = {}
        for code in supported_codes:
            value = raw_rates.get(code)
            if isinstance(value, (int, float)) and value > 0:
                rates[code] = float(value)

        if "USD" not in rates:
            rates["USD"] = 1.0
        if len(rates) < 2:
            return fallback

        for code in supported_codes:
            rates.setdefault(code, FALLBACK_RATES_PER_USD[code])

        updated_at = self._parse_updated_at(data, now)
        return self._build_payload(
            rates=rates,
            updated_at=updated_at,
            source=settings.CURRENCY_RATES_URL,
            is_fallback=False,
        )

    def _supported_codes(self) -> list[str]:
        seen: set[str] = set()
        codes: list[str] = []
        for raw_code in settings.DISPLAY_CURRENCIES:
            code = str(raw_code).upper()
            if code in seen or code not in FALLBACK_RATES_PER_USD:
                continue
            seen.add(code)
            codes.append(code)
        return codes or ["USD", "CNY"]

    def _build_payload(
        self,
        *,
        rates: dict[str, float],
        updated_at: datetime,
        source: str,
        is_fallback: bool,
    ) -> dict[str, Any]:
        supported = []
        for code in self._supported_codes():
            meta = DISPLAY_CURRENCY_META[code]
            supported.append({"code": code, **meta})

        aliases = {code: code for code in self._supported_codes()}
        for symbol in get_usd_equivalent_symbols():
            aliases[str(symbol).upper()] = "USD"

        return {
            "base": "USD",
            "rates": {code: rates[code] for code in self._supported_codes()},
            "supported": supported,
            "aliases": aliases,
            "updated_at": updated_at.isoformat(),
            "source": source,
            "is_fallback": is_fallback,
        }

    @staticmethod
    def _parse_updated_at(data: dict[str, Any], fallback: datetime) -> datetime:
        unix_time = data.get("time_last_update_unix")
        if isinstance(unix_time, (int, float)) and unix_time > 0:
            return datetime.fromtimestamp(float(unix_time), tz=timezone.utc)
        date_text = data.get("date")
        if isinstance(date_text, str):
            try:
                return datetime.fromisoformat(date_text).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return fallback
