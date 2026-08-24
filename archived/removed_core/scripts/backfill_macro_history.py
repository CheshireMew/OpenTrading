from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.application.indicators.market_cron import INDICATOR_META
from app.infra.db import build_database_runtime
from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
from app.services.fred_api_config_service import get_fred_api_key
from config import settings


FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
TREASURY_TGA_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
NYFED_SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
NYFED_REVERSE_REPO_URL = "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json"


@dataclass(frozen=True)
class FredSeries:
    indicator_id: str
    series_id: str


FRED_SERIES: tuple[FredSeries, ...] = (
    FredSeries("US10Y", "DGS10"),
    FredSeries("US02Y", "DGS2"),
    FredSeries("NASDAQ", "NASDAQCOM"),
    FredSeries("HY_SPREAD", "BAMLH0A0HYM2"),
    FredSeries("FED_RATE", "FEDFUNDS"),
    FredSeries("FED_BALANCE", "WALCL"),
    FredSeries("M2", "M2SL"),
    FredSeries("VIX", "VIXCLS"),
    FredSeries("DXY", "DTWEXBGS"),
    FredSeries("WTI", "DCOILWTICO"),
)


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def parse_float(value: Any) -> float | None:
    if value in (None, "", ".", "null"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def daterange_year_chunks(start_date: str, end_date: str) -> Iterable[tuple[str, str]]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=366), end)
        yield cursor.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        cursor = chunk_end + timedelta(days=1)


def fetch_fred_series(series: FredSeries, start_date: str, end_date: str, api_key: str) -> list[dict[str, Any]]:
    params = {
        "series_id": series.series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc",
        "observation_start": start_date,
        "observation_end": end_date,
        "limit": 100000,
    }
    response = requests.get(FRED_BASE_URL, params=params, timeout=settings.FRED_REQUEST_TIMEOUT)
    response.raise_for_status()
    points = []
    for item in response.json().get("observations", []):
        value = parse_float(item.get("value"))
        if value is None:
            continue
        points.append(
            {
                "indicator_id": series.indicator_id,
                "timestamp": parse_date(item["date"]),
                "value": value,
            }
        )
    return points


def fetch_treasury_tga(start_date: str, end_date: str) -> list[dict[str, Any]]:
    params = {
        "fields": "record_date,account_type,open_today_bal",
        "filter": (
            f"record_date:gte:{start_date},"
            f"record_date:lte:{end_date},"
            "account_type:eq:Treasury General Account (TGA) Closing Balance"
        ),
        "sort": "record_date",
        "page[size]": 10000,
    }
    response = requests.get(TREASURY_TGA_URL, params=params, timeout=30)
    response.raise_for_status()
    points = []
    for item in response.json().get("data", []):
        value = parse_float(item.get("open_today_bal"))
        if value is None:
            continue
        points.append(
            {
                "indicator_id": "TGA",
                "timestamp": parse_date(item["record_date"]),
                "value": value,
            }
        )
    return points


def fetch_nyfed_sofr(start_date: str, end_date: str) -> list[dict[str, Any]]:
    points = []
    for chunk_start, chunk_end in daterange_year_chunks(start_date, end_date):
        response = requests.get(
            NYFED_SOFR_URL,
            params={"startDate": chunk_start, "endDate": chunk_end},
            timeout=30,
        )
        response.raise_for_status()
        for item in response.json().get("refRates", []):
            if item.get("type") != "SOFR":
                continue
            value = parse_float(item.get("percentRate"))
            if value is None:
                continue
            points.append(
                {
                    "indicator_id": "SOFR",
                    "timestamp": parse_date(item["effectiveDate"]),
                    "value": value,
                }
            )
    return points


def fetch_nyfed_onrrp(start_date: str, end_date: str) -> list[dict[str, Any]]:
    points = []
    for chunk_start, chunk_end in daterange_year_chunks(start_date, end_date):
        response = requests.get(
            NYFED_REVERSE_REPO_URL,
            params={"startDate": chunk_start, "endDate": chunk_end},
            timeout=30,
        )
        response.raise_for_status()
        operations = response.json().get("repo", {}).get("operations", [])
        for item in operations:
            if item.get("operationType") != "Reverse Repo":
                continue
            value = parse_float(item.get("totalAmtAccepted"))
            if value is None:
                continue
            points.append(
                {
                    "indicator_id": "ONRRP",
                    "timestamp": parse_date(item["operationDate"]),
                    "value": value / 1_000_000_000,
                }
            )
    return points


def fetch_all(start_date: str, end_date: str) -> list[dict[str, Any]]:
    fred_api_key = get_fred_api_key()
    if not fred_api_key:
        raise RuntimeError("FRED API key is not configured; set it in Settings or .env before backfilling.")

    points: list[dict[str, Any]] = []
    for series in FRED_SERIES:
        series_points = fetch_fred_series(series, start_date, end_date, fred_api_key)
        print(f"FRED {series.series_id} -> {series.indicator_id}: {len(series_points)} points")
        points.extend(series_points)

    tga_points = fetch_treasury_tga(start_date, end_date)
    print(f"Treasury DTS -> TGA: {len(tga_points)} points")
    points.extend(tga_points)

    sofr_points = fetch_nyfed_sofr(start_date, end_date)
    print(f"NY Fed SOFR -> SOFR: {len(sofr_points)} points")
    points.extend(sofr_points)

    onrrp_points = fetch_nyfed_onrrp(start_date, end_date)
    print(f"NY Fed Reverse Repo -> ONRRP: {len(onrrp_points)} points")
    points.extend(onrrp_points)
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill macro indicator history from FRED, Treasury, and NY Fed.")
    parser.add_argument("--start-date", default="2014-01-01", help="Start date, YYYY-MM-DD")
    parser.add_argument("--end-date", default=datetime.now().strftime("%Y-%m-%d"), help="End date, YYYY-MM-DD")
    args = parser.parse_args()

    points = fetch_all(args.start_date, args.end_date)
    repository = MarketIndicatorRepository(database_runtime=build_database_runtime(settings))
    repository.upsert_points(points, INDICATOR_META)
    print(f"Saved {len(points)} macro history points")


if __name__ == "__main__":
    main()
