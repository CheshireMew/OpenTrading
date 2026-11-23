from __future__ import annotations

from dataclasses import dataclass
from contextlib import redirect_stdout
from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Any, Protocol
import sys

import pandas as pd

from app.infra.market_data.binance_client import BinanceKlineClient
from app.infra.market_data.fred_client import FredObservationClient
from app.infra.market_data.http import HttpTransport, UrllibJsonTransport
from app.infra.market_data.tiingo_client import TiingoDailyClient
from app.domain.immutability import deep_freeze
from app.domain.market.history.models import Instrument, PriceBar
from app.infra.persistence.market.history.catalog_repository import CatalogRepository
from app.infra.persistence.market.history.database import MarketHistoryDatabase


@dataclass(frozen=True, slots=True)
class ProviderFetch:
    provider: str
    provider_symbol: str
    payload: Any
    bars: tuple[PriceBar, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", deep_freeze(self.payload))


class PriceProvider(Protocol):
    name: str

    def fetch(self, instrument: Instrument, provider_symbol: str, start: date, end: date) -> ProviderFetch: ...


class YFinanceProvider:
    name = "yfinance"

    def fetch(self, instrument: Instrument, provider_symbol: str, start: date, end: date) -> ProviderFetch:
        import yfinance as yf

        frame = yf.Ticker(provider_symbol).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
            repair=True,
            timeout=30,
        )
        if frame.empty:
            raise ValueError(f"yfinance returned no data for {provider_symbol}")
        payload = _frame_payload(frame)
        bars = []
        repaired_bounds = 0
        for timestamp, row in frame.iterrows():
            observed = _utc_midnight(pd.Timestamp(timestamp).date())
            close = _number(row.get("Close"))
            adjusted = _number(row.get("Adj Close")) or close
            open_value = _required_number(row.get("Open"), "Open")
            close_value = _required_number(close, "Close")
            supplied_high = _required_number(row.get("High"), "High")
            supplied_low = _required_number(row.get("Low"), "Low")
            high_value = max(supplied_high, open_value, close_value)
            low_value = min(supplied_low, open_value, close_value)
            repaired_bounds += int(high_value != supplied_high or low_value != supplied_low)
            volume = _number(row.get("Volume"))
            if volume == 0 and instrument.asset_class in {"fx", "index"}:
                volume = None
            bars.append(
                PriceBar(
                    observed_at=observed,
                    open=open_value,
                    high=high_value,
                    low=low_value,
                    close=close_value,
                    adjusted_close=_required_number(adjusted, "Adj Close"),
                    volume=volume,
                    dividend=_number(row.get("Dividends")) or 0.0,
                    split_factor=_split_factor(row.get("Stock Splits")),
                )
            )
        warnings = (
            (f"normalized {repaired_bounds} provider OHLC bounds to include open and close",)
            if repaired_bounds else ()
        )
        return ProviderFetch(
            self.name, provider_symbol, payload,
            tuple(sorted(bars, key=lambda item: item.observed_at)), warnings,
        )


class AkShareProvider:
    name = "akshare"

    def fetch(self, instrument: Instrument, provider_symbol: str, start: date, end: date) -> ProviderFetch:
        import akshare as ak

        start_text = start.strftime("%Y%m%d")
        end_text = end.strftime("%Y%m%d")
        if instrument.asset_class == "commodity":
            raw = ak.futures_foreign_hist(symbol=provider_symbol)
            raw = _filter_frame_dates(raw, start, end)
            adjusted = raw.copy()
        elif instrument.market == "CN" and instrument.asset_class == "etf":
            raw = ak.fund_etf_hist_em(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="",
            )
            adjusted = ak.fund_etf_hist_em(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="qfq",
            )
        elif instrument.market == "CN" and instrument.asset_class == "index":
            raw = ak.stock_zh_index_daily_em(symbol=provider_symbol, start_date=start_text, end_date=end_text)
            adjusted = raw.copy()
        elif instrument.market == "CN":
            raw = ak.stock_zh_a_hist(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="",
            )
            adjusted = ak.stock_zh_a_hist(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="qfq",
            )
        elif instrument.market == "HK":
            raw = ak.stock_hk_hist(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="",
            )
            adjusted = ak.stock_hk_hist(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="qfq",
            )
        elif instrument.market == "US":
            raw = ak.stock_us_hist(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="",
            )
            adjusted = ak.stock_us_hist(
                symbol=provider_symbol, period="daily", start_date=start_text, end_date=end_text, adjust="qfq",
            )
        else:
            raise ValueError(f"AKShare does not support {instrument.canonical_code}")
        if raw.empty:
            raise ValueError(f"AKShare returned no data for {provider_symbol}")
        bars = _bars_from_chinese_frame(raw, adjusted)
        return ProviderFetch(
            self.name, provider_symbol,
            {"raw": _frame_payload(raw), "adjusted": _frame_payload(adjusted)},
            bars,
        )


class BaoStockProvider:
    name = "baostock"

    def fetch(self, instrument: Instrument, provider_symbol: str, start: date, end: date) -> ProviderFetch:
        if instrument.market != "CN":
            raise ValueError("BaoStock is used only for mainland China instruments")
        import baostock as bs

        with redirect_stdout(sys.stderr):
            login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
        fields = "date,open,high,low,close,volume"
        try:
            raw = _baostock_rows(
                bs.query_history_k_data_plus(
                    provider_symbol, fields, start_date=start.isoformat(), end_date=end.isoformat(),
                    frequency="d", adjustflag="3",
                )
            )
            adjusted = _baostock_rows(
                bs.query_history_k_data_plus(
                    provider_symbol, fields, start_date=start.isoformat(), end_date=end.isoformat(),
                    frequency="d", adjustflag="2",
                )
            )
        finally:
            with redirect_stdout(sys.stderr):
                bs.logout()
        if not raw:
            raise ValueError(f"BaoStock returned no data for {provider_symbol}")
        adjusted_by_date = {row["date"]: row for row in adjusted}
        bars = tuple(
            PriceBar(
                observed_at=_utc_midnight(date.fromisoformat(row["date"])),
                open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                close=float(row["close"]),
                adjusted_close=float(adjusted_by_date.get(row["date"], row)["close"]),
                volume=_number(row["volume"]),
            )
            for row in raw if row["close"]
        )
        return ProviderFetch(self.name, provider_symbol, {"raw": raw, "adjusted": adjusted}, bars)


class BinanceSpotProvider:
    name = "binance"

    def __init__(self, transport: HttpTransport | None = None) -> None:
        self.transport = transport or UrllibJsonTransport()
        self._client = BinanceKlineClient(self.transport)

    def fetch(self, instrument: Instrument, provider_symbol: str, start: date, end: date) -> ProviderFetch:
        if instrument.exchange != "BINANCE" or instrument.metadata.get("contract_type") == "perpetual":
            raise ValueError("Binance spot provider cannot serve a perpetual contract")
        start_ms = int(datetime.combine(start, time.min, timezone.utc).timestamp() * 1000)
        end_ms = int(datetime.combine(end + timedelta(days=1), time.min, timezone.utc).timestamp() * 1000)
        payload = self._client.download_klines(
            spot=True,
            symbol=provider_symbol,
            interval="1d",
            start_ms=start_ms,
            end_ms=end_ms,
        )
        if not payload:
            raise ValueError(f"Binance spot returned no data for {provider_symbol}")
        bars = tuple(
            PriceBar(
                observed_at=datetime.fromtimestamp(int(row[0]) / 1000, timezone.utc),
                open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]),
                adjusted_close=float(row[4]), volume=float(row[5]),
            )
            for row in payload
        )
        return ProviderFetch(
            self.name, provider_symbol, payload,
            tuple(sorted(bars, key=lambda item: item.observed_at)),
        )


class FredPriceProvider:
    name = "fred"

    def __init__(self, api_key: str = "", transport: HttpTransport | None = None) -> None:
        self.api_key = api_key
        self.transport = transport or UrllibJsonTransport()
        self._client = FredObservationClient(api_key, self.transport)

    def fetch(self, instrument: Instrument, provider_symbol: str, start: date, end: date) -> ProviderFetch:
        try:
            payload, _transport_name = self._client.fetch_latest(
                provider_symbol,
                start,
                end,
            )
        except Exception as exc:
            source = "FRED price-series" if self.api_key else "FRED public CSV price-series"
            raise RuntimeError(f"{source} request failed") from exc
        rows = payload.get("observations", []) if isinstance(payload, dict) else []
        bars = []
        for row in rows:
            if row.get("value") in {None, "", "."}:
                continue
            value = float(row["value"])
            bars.append(
                PriceBar(
                    observed_at=_utc_midnight(date.fromisoformat(row["date"])),
                    open=value, high=value, low=value, close=value, adjusted_close=value,
                )
            )
        if not bars:
            raise ValueError(f"FRED returned no data for {provider_symbol}")
        return ProviderFetch(self.name, provider_symbol, payload, tuple(bars))


class TiingoPriceProvider:
    name = "tiingo"

    def __init__(self, token: str, transport: HttpTransport | None = None) -> None:
        if not token:
            raise ValueError("TIINGO_API_TOKEN is required for the Tiingo provider")
        self.token = token
        self.transport = transport or UrllibJsonTransport()
        self._client = TiingoDailyClient(token, self.transport)

    def fetch(self, instrument: Instrument, provider_symbol: str, start: date, end: date) -> ProviderFetch:
        payload = self._client.fetch(provider_symbol, start, end)
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"Tiingo returned no data for {provider_symbol}")
        bars = tuple(
            PriceBar(
                observed_at=_utc_midnight(datetime.fromisoformat(row["date"].replace("Z", "+00:00")).date()),
                open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                close=float(row["close"]), adjusted_close=float(row["adjClose"]),
                volume=_number(row.get("volume")), dividend=float(row.get("divCash", 0)),
                split_factor=float(row.get("splitFactor", 1)),
            )
            for row in payload
        )
        return ProviderFetch(self.name, provider_symbol, payload, bars)


def provider_order(instrument: Instrument, explicit: str | None = None) -> tuple[str, ...]:
    if explicit:
        return (explicit.casefold(),)
    if instrument.asset_class == "crypto":
        return ("binance",)
    if instrument.market == "CN":
        return ("akshare", "baostock")
    if instrument.market in {"US", "HK"} or instrument.asset_class in {"stock", "etf", "index"}:
        return ("yfinance", "akshare")
    if instrument.asset_class == "fx":
        return ("yfinance", "fred")
    if instrument.asset_class == "commodity":
        return ("yfinance", "akshare")
    raise ValueError(f"no price provider is configured for {instrument.canonical_code}")


def make_provider(
    name: str,
    *,
    fred_api_key: str = "",
    tiingo_token: str = "",
    transport: HttpTransport | None = None,
) -> PriceProvider:
    if name == "yfinance":
        return YFinanceProvider()
    if name == "akshare":
        return AkShareProvider()
    if name == "baostock":
        return BaoStockProvider()
    if name == "binance":
        return BinanceSpotProvider(transport)
    if name == "fred":
        return FredPriceProvider(fred_api_key, transport)
    if name == "tiingo":
        return TiingoPriceProvider(tiingo_token, transport)
    raise ValueError(f"unsupported provider: {name}")


def provider_symbol(database: MarketHistoryDatabase, instrument: Instrument, provider: str) -> str:
    mapped = CatalogRepository(database).provider_mapping(instrument.canonical_code, provider)
    if mapped:
        return mapped
    from app.domain.market.history.catalog_conventions import default_provider_mappings

    mapped = default_provider_mappings(instrument).get(provider)
    if not mapped:
        raise ValueError(f"{provider} has no symbol mapping for {instrument.canonical_code}")
    return mapped


def _bars_from_chinese_frame(raw: pd.DataFrame, adjusted: pd.DataFrame) -> tuple[PriceBar, ...]:
    raw_records = _standardize_chinese_records(raw)
    adjusted_records = {item["date"]: item for item in _standardize_chinese_records(adjusted)}
    bars = []
    for item in raw_records:
        adjusted_item = adjusted_records.get(item["date"], item)
        bars.append(
            PriceBar(
                observed_at=_utc_midnight(date.fromisoformat(item["date"])),
                open=float(item["open"]), high=float(item["high"]), low=float(item["low"]),
                close=float(item["close"]), adjusted_close=float(adjusted_item["close"]),
                volume=_number(item.get("volume")),
            )
        )
    return tuple(sorted(bars, key=lambda item: item.observed_at))


def _standardize_chinese_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    aliases = {
        "date": ("日期", "date", "时间"), "open": ("开盘", "open"),
        "high": ("最高", "high"), "low": ("最低", "low"), "close": ("收盘", "close"),
        "volume": ("成交量", "volume", "成交量/手"),
    }
    columns = {}
    for target, candidates in aliases.items():
        columns[target] = next((candidate for candidate in candidates if candidate in frame.columns), None)
    required = ("date", "open", "high", "low", "close")
    if any(columns[key] is None for key in required):
        raise ValueError(f"provider response is missing OHLC columns: {list(frame.columns)}")
    output = []
    for _, row in frame.iterrows():
        observed = pd.Timestamp(row[columns["date"]]).date()
        output.append(
            {
                "date": observed.isoformat(),
                "open": row[columns["open"]], "high": row[columns["high"]],
                "low": row[columns["low"]], "close": row[columns["close"]],
                "volume": row[columns["volume"]] if columns["volume"] else None,
            }
        )
    return output


def _baostock_rows(result: Any) -> list[dict[str, str]]:
    if result.error_code != "0":
        raise RuntimeError(f"BaoStock request failed: {result.error_msg}")
    rows = []
    while result.error_code == "0" and result.next():
        rows.append(dict(zip(result.fields, result.get_row_data(), strict=True)))
    return rows


def _frame_payload(frame: pd.DataFrame) -> list[dict[str, Any]]:
    reset = frame.reset_index()
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in reset.to_dict("records")
    ]


def _filter_frame_dates(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    date_column = next((item for item in ("日期", "date", "时间") if item in frame.columns), None)
    if not date_column:
        raise ValueError("AKShare commodity response has no date column")
    dates = pd.to_datetime(frame[date_column]).dt.date
    return frame.loc[(dates >= start) & (dates <= end)].copy()


def _utc_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, timezone.utc)


def _number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _required_number(value: Any, label: str) -> float:
    numeric = _number(value)
    if numeric is None:
        raise ValueError(f"provider returned an invalid {label} value")
    return numeric


def _split_factor(value: Any) -> float:
    numeric = _number(value)
    return numeric if numeric and numeric > 0 else 1.0


def _json_value(value: Any) -> Any:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value
