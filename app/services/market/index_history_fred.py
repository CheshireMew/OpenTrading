from __future__ import annotations

import csv
import io
from datetime import datetime

import requests

from app.domain.market.index_catalog import IndexInstrument
from app.services.market.index_history_contracts import IndexFetchResult
from app.services.market.index_history_parsing import IndexHistoryParsing
from app.services.market.index_source_catalog import IndexSourceBinding
from app.services.fred_api_config_service import read_fred_api_key
from config import settings


class FredIndexHistoryProvider(IndexHistoryParsing):
    def fetch_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.fred_series_id:
            return IndexFetchResult(data=[], source="fred")

        fred_api_key = read_fred_api_key()
        if fred_api_key:
            result = self._fetch_api_history(source, start_dt, end_dt, fred_api_key)
            if result.data:
                return result

        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": source.fred_series_id},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=settings.FRED_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        data: list[list[float]] = []
        for row in reader:
            date_text = row.get("observation_date") or row.get("DATE") or row.get("date")
            value_text = row.get(source.fred_series_id)
            if not date_text or not value_text or value_text == ".":
                continue
            row_dt = self.parse_date(date_text)
            if row_dt < start_dt or row_dt > end_dt:
                continue
            value = float(value_text)
            data.append([self.to_ms(row_dt), value, value, value, value, 0.0])
        return IndexFetchResult(data=data, source="fred", is_close_only=True)

    def fetch_usd_fx_rates(
        self,
        currency: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, float]:
        response = requests.get(
            f"https://api.frankfurter.app/{start_dt.strftime('%Y-%m-%d')}..{end_dt.strftime('%Y-%m-%d')}",
            params={"from": currency, "to": "USD"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        rates = payload.get("rates") or {}
        return {
            date_text: float((values or {}).get("USD"))
            for date_text, values in rates.items()
            if (values or {}).get("USD") is not None
        }

    def _fetch_api_history(
        self,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
        fred_api_key: str,
    ) -> IndexFetchResult:
        response = requests.get(
            settings.FRED_API_URL,
            params={
                "series_id": source.fred_series_id,
                "api_key": fred_api_key,
                "file_type": "json",
                "observation_start": start_dt.strftime("%Y-%m-%d"),
                "observation_end": end_dt.strftime("%Y-%m-%d"),
            },
            timeout=settings.FRED_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data: list[list[float]] = []
        for row in response.json().get("observations", []):
            value_text = row.get("value")
            if not value_text or value_text == ".":
                continue
            value = float(value_text)
            data.append([
                self.to_ms(self.parse_date(row["date"])),
                value,
                value,
                value,
                value,
                0.0,
            ])
        return IndexFetchResult(data=data, source="fred", is_close_only=True)
