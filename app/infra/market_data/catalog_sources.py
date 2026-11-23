from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import redirect_stdout
from datetime import date
import csv
from io import BytesIO, StringIO
import sys
from typing import Any

import pandas as pd

from app.infra.market_data.http import HttpTransport
from app.domain.market.history.catalog_conventions import (
    default_provider_mappings,
    infer_instrument,
)
from app.domain.market.history.catalog_record import CatalogRecord
from app.domain.market.history.models import AssetClass, Instrument


def catalog_source_loaders(
    transport: HttpTransport,
) -> tuple[
    list[tuple[str, Callable[[], Iterable[CatalogRecord]]]],
    list[str],
    list[dict[str, Any]],
]:
    loaders: list[tuple[str, Callable[[], Iterable[CatalogRecord]]]] = []
    warnings: list[str] = []
    attempts: list[dict[str, Any]] = []
    try:
        import akshare as ak
    except Exception as exc:
        warnings.append(f"AKShare import failed: {exc}")
        attempts.append({"source": "akshare", "status": "error", "error": str(exc)})
    else:
        loaders.extend(
            (
                ("akshare_A-share", lambda: _akshare_a_records(ak.stock_info_a_code_name())),
                (
                    "akshare_mainland ETF",
                    lambda: _akshare_cn_etf_records(ak.fund_etf_spot_em()),
                ),
                (
                    "akshare_mainland index",
                    lambda: _akshare_index_records(ak.stock_zh_index_spot_em()),
                ),
                (
                    "akshare_US security",
                    lambda: _akshare_us_records(ak.stock_us_spot_em()),
                ),
                (
                    "akshare_Hong Kong security",
                    lambda: _akshare_hk_records(ak.stock_hk_spot_em()),
                ),
            )
        )
    loaders.extend(
        (
            ("baostock_mainland", _baostock_cn_records),
            ("nasdaq_trader_us", lambda: _nasdaq_trader_us_records(transport)),
            ("hkex_hong_kong", lambda: _hkex_hong_kong_records(transport)),
        )
    )
    return loaders, warnings, attempts


def _akshare_a_records(frame: Any) -> Iterable[CatalogRecord]:
    for row in frame.to_dict("records"):
        code = str(row.get("code") or row.get("代码") or "").zfill(6)
        name = str(row.get("name") or row.get("名称") or "").strip()
        suffix = "SH" if code.startswith("6") else "BJ" if code.startswith(("4", "8")) else "SZ"
        if code and name:
            instrument = infer_instrument(f"{code}.{suffix}")
            if instrument:
                instrument = Instrument(
                    instrument.canonical_code, name, instrument.asset_class, instrument.market,
                    instrument.exchange, instrument.currency, instrument.timezone,
                )
                yield CatalogRecord(
                    instrument, {(name, "chinese_name"), (code, "common_code")},
                    default_provider_mappings(instrument), priority=1,
                )


def _akshare_cn_etf_records(frame: Any) -> Iterable[CatalogRecord]:
    for row in frame.to_dict("records"):
        code = str(row.get("代码") or "").zfill(6)
        name = str(row.get("名称") or "").strip()
        suffix = "SH" if code.startswith(("5", "6")) else "SZ"
        if not code or not name:
            continue
        instrument = Instrument(
            f"{code}.{suffix}", name, "etf", "CN", "XSHG" if suffix == "SH" else "XSHE",
            "CNY", "Asia/Shanghai",
        )
        yield CatalogRecord(
            instrument, {(name, "chinese_name"), (code, "common_code")},
            {"akshare": code, "baostock": f"{suffix.casefold()}.{code}"}, priority=2,
        )


def _akshare_index_records(frame: Any) -> Iterable[CatalogRecord]:
    for row in frame.to_dict("records"):
        raw_code = str(row.get("代码") or "").strip()
        market_prefix, _, numeric = raw_code.rpartition(".")
        code = numeric if numeric else raw_code
        name = str(row.get("名称") or "").strip()
        if not code or not name:
            continue
        exchange_prefix = "sz" if market_prefix == "0" or code.startswith("399") else "sh"
        canonical = f"{exchange_prefix.upper()}{code.upper()}.INDEX"
        instrument = Instrument(
            canonical, name, "index", "CN", "XSHE" if exchange_prefix == "sz" else "XSHG",
            "CNY", "Asia/Shanghai",
        )
        yield CatalogRecord(
            instrument, {(name, "chinese_name"), (raw_code, "common_code")},
            {"akshare": f"{exchange_prefix}{code}", "baostock": f"{exchange_prefix}.{code}"}, priority=1,
        )


def _akshare_us_records(frame: Any) -> Iterable[CatalogRecord]:
    for row in frame.to_dict("records"):
        ak_code = str(row.get("代码") or "").strip()
        ticker = ak_code.rsplit(".", 1)[-1].upper()
        name = str(row.get("名称") or "").strip()
        if not ticker or not name:
            continue
        asset_class: AssetClass = "etf" if "ETF" in name.upper() else "stock"
        instrument = Instrument(
            f"{ticker}.US", name, asset_class, "US", "US", "USD", "America/New_York",
        )
        yield CatalogRecord(
            instrument, {(name, "english_name"), (ticker, "common_code")},
            {"akshare": ak_code, "yfinance": ticker, "tiingo": ticker}, priority=1,
        )


def _akshare_hk_records(frame: Any) -> Iterable[CatalogRecord]:
    for row in frame.to_dict("records"):
        raw_code = str(row.get("代码") or "").strip()
        code = raw_code.zfill(5)
        name = str(row.get("名称") or "").strip()
        if not code or not name:
            continue
        instrument = Instrument(
            f"{code}.HK", name, "stock", "HK", "XHKG", "HKD", "Asia/Hong_Kong",
        )
        yield CatalogRecord(
            instrument, {(name, "chinese_name"), (raw_code, "common_code")},
            {"akshare": code, "yfinance": f"{int(code):04d}.HK"}, priority=1,
        )


def _baostock_cn_records() -> Iterable[CatalogRecord]:
    import baostock as bs

    with redirect_stdout(sys.stderr):
        login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
    try:
        result = bs.query_stock_basic()
        if result.error_code != "0":
            raise RuntimeError(f"BaoStock catalog failed: {result.error_msg}")
        records = []
        while result.error_code == "0" and result.next():
            records.append(dict(zip(result.fields, result.get_row_data(), strict=True)))
    finally:
        with redirect_stdout(sys.stderr):
            bs.logout()
    for row in records:
        provider_code = row.get("code", "")
        prefix, _, number = provider_code.partition(".")
        name = row.get("code_name", "").strip()
        kind = row.get("type", "")
        if prefix not in {"sh", "sz", "bj"} or not number or not name:
            continue
        suffix = prefix.upper()
        listed_on = date.fromisoformat(row["ipoDate"]) if row.get("ipoDate") else None
        if kind == "2":
            instrument = Instrument(
                f"{suffix}{number}.INDEX", name, "index", "CN",
                "XSHG" if suffix == "SH" else "XSHE", "CNY", "Asia/Shanghai", listed_on,
            )
            mappings = {"baostock": provider_code, "akshare": f"{prefix}{number}"}
        else:
            asset_class: AssetClass = "etf" if kind == "5" else "stock"
            instrument = Instrument(
                f"{number}.{suffix}", name, asset_class, "CN",
                "XSHG" if suffix == "SH" else "XSHE" if suffix == "SZ" else "BJ",
                "CNY", "Asia/Shanghai", listed_on,
            )
            mappings = {"baostock": provider_code, "akshare": number}
        yield CatalogRecord(
            instrument, {(name, "chinese_name"), (number, "common_code")}, mappings,
            priority=2 if instrument.asset_class == "etf" else 1,
        )


def _nasdaq_trader_us_records(transport: HttpTransport) -> Iterable[CatalogRecord]:
    sources = (
        ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "Symbol", "XNAS"),
        ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "ACT Symbol", "US"),
    )
    for url, symbol_field, exchange in sources:
        text = transport.get_bytes(
            url,
            headers={},
        ).decode("utf-8-sig")
        for row in csv.DictReader(StringIO(text), delimiter="|"):
            ticker = str(row.get(symbol_field) or "").strip().upper()
            name = str(row.get("Security Name") or "").strip()
            if not ticker or not name or ticker.startswith("File Creation Time"):
                continue
            if row.get("Test Issue") == "Y":
                continue
            asset_class: AssetClass = "etf" if row.get("ETF") == "Y" else "stock"
            canonical_ticker = ticker.replace("/", "-")
            instrument = Instrument(
                f"{canonical_ticker}.US", name, asset_class, "US", exchange,
                "USD", "America/New_York", metadata={"catalog_source": "nasdaq_trader"},
            )
            yield CatalogRecord(
                instrument,
                {(ticker, "common_code"), (name, "english_name")},
                {
                    "yfinance": ticker.replace(".", "-"),
                    "tiingo": ticker,
                },
                priority=2,
            )


def _hkex_hong_kong_records(transport: HttpTransport) -> Iterable[CatalogRecord]:
    url = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
    content = transport.get_bytes(
        url,
        headers={},
        max_response_bytes=32 * 1024 * 1024,
    )
    frame = pd.read_excel(BytesIO(content), header=2)
    supported: dict[str, AssetClass] = {
        "Equity": "stock",
        "Exchange Traded Products": "etf",
        "Real Estate Investment Trusts": "stock",
    }
    for row in frame.to_dict("records"):
        category = str(row.get("Category") or "").strip()
        asset_class = supported.get(category)
        if not asset_class:
            continue
        raw_code = row.get("Stock Code")
        if pd.isna(raw_code):
            continue
        code = str(int(raw_code)).zfill(5)
        name = str(row.get("Name of Securities") or "").strip()
        if not name:
            continue
        raw_currency = row.get("Trading Currency")
        currency = "HKD" if pd.isna(raw_currency) else str(raw_currency).strip()
        currency = "CNY" if currency == "RMB" else currency
        raw_isin = row.get("ISIN")
        instrument = Instrument(
            f"{code}.HK", name, asset_class, "HK", "XHKG", currency, "Asia/Hong_Kong",
            metadata={
                "catalog_source": "hkex",
                "category": category,
                "sub_category": str(row.get("Sub-Category") or "").strip(),
                "isin": "" if pd.isna(raw_isin) else str(raw_isin).strip(),
            },
        )
        yield CatalogRecord(
            instrument,
            {(name, "english_name"), (str(int(raw_code)), "common_code")},
            {"yfinance": f"{int(raw_code):04d}.HK", "akshare": code},
            priority=2,
        )
