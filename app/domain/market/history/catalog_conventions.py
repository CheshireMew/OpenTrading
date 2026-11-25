from __future__ import annotations

import re

from app.domain.market.history.models import AssetClass, Instrument


CANONICAL_PATTERNS = (
    re.compile(r"^[A-Z0-9.^-]+\.(US|SH|SZ|BJ|HK)$"),
    re.compile(r"^[A-Z0-9.^-]+\.INDEX$"),
    re.compile(r"^[A-Z0-9]+/[A-Z0-9]+@[A-Z0-9_-]+$"),
    re.compile(r"^[A-Z]{3}/[A-Z]{3}$"),
    re.compile(r"^[A-Z0-9]+\.[A-Z0-9_-]+$"),
    re.compile(r"^FRED:[A-Z0-9_-]+$"),
)

INDEX_PROVIDER_SYMBOLS = {
    "SPX.INDEX": "^GSPC",
    "DJI.INDEX": "^DJI",
    "IXIC.INDEX": "^IXIC",
    "NDX.INDEX": "^NDX",
    "RUT.INDEX": "^RUT",
    "VIX.INDEX": "^VIX",
    "DXY.INDEX": "DX-Y.NYB",
    "HSI.INDEX": "^HSI",
}

FX_FRED_SERIES = {
    "EUR/USD": "DEXUSEU",
    "USD/JPY": "DEXJPUS",
    "GBP/USD": "DEXUSUK",
    "AUD/USD": "DEXUSAL",
    "USD/CAD": "DEXCAUS",
    "USD/CHF": "DEXSZUS",
    "NZD/USD": "DEXUSNZ",
}

def infer_instrument(canonical_code: str) -> Instrument | None:
    code = canonical_code.upper()
    if code.startswith("FRED:"):
        return Instrument(code, code[5:], "macro", "US", "FRED", "index", "UTC")
    if "@" in code and "/" in code:
        pair, exchange = code.split("@", 1)
        return Instrument(code, pair, "crypto", "crypto", exchange, pair.split("/")[1], "UTC")
    if re.fullmatch(r"[A-Z]{3}/[A-Z]{3}", code):
        return Instrument(code, code, "fx", "global", "OTC", code.split("/")[1], "UTC")
    if code.endswith(".INDEX"):
        return Instrument(code, code.removesuffix(".INDEX"), "index", "global", "INDEX", "index", "UTC")
    if code.endswith(".US"):
        return Instrument(code, code.removesuffix(".US"), "stock", "US", "US", "USD", "America/New_York")
    if code.endswith((".SH", ".SZ", ".BJ")):
        exchange = code.rsplit(".", 1)[1]
        number = code.split(".", 1)[0]
        asset_class: AssetClass = "etf" if (
            (exchange == "SH" and number.startswith("5"))
            or (exchange == "SZ" and number.startswith(("15", "16")))
        ) else "stock"
        return Instrument(code, number, asset_class, "CN", exchange, "CNY", "Asia/Shanghai")
    if code.endswith(".HK"):
        return Instrument(code, code.removesuffix(".HK"), "stock", "HK", "XHKG", "HKD", "Asia/Hong_Kong")
    if re.fullmatch(r"[A-Z0-9]+\.[A-Z0-9_-]+", code):
        exchange = code.rsplit(".", 1)[1]
        return Instrument(code, code.split(".", 1)[0], "commodity", "global", exchange, "USD", "UTC", is_continuous=True)
    return None


def default_provider_mappings(instrument: Instrument) -> dict[str, str]:
    code = instrument.canonical_code
    if instrument.asset_class == "crypto":
        return {"binance": code.split("@", 1)[0].replace("/", "")}
    if instrument.asset_class == "fx":
        base, quote = code.split("/")
        mappings = {"yfinance": f"{base}{quote}=X"}
        if code in FX_FRED_SERIES:
            mappings["fred"] = FX_FRED_SERIES[code]
        return mappings
    if instrument.asset_class == "index" and code in INDEX_PROVIDER_SYMBOLS:
        return {"yfinance": INDEX_PROVIDER_SYMBOLS[code]}
    if instrument.asset_class == "commodity":
        match = re.fullmatch(r"([A-Z]+)1\.([A-Z0-9_-]+)", code)
        if match:
            root = match.group(1)
            return {"yfinance": f"{root}=F", "akshare": root}
    if code.endswith(".US"):
        return {"yfinance": code.removesuffix(".US"), "tiingo": code.removesuffix(".US")}
    if code.endswith(".SH"):
        number = code.removesuffix(".SH")
        return {"akshare": number, "baostock": f"sh.{number}"}
    if code.endswith(".SZ"):
        number = code.removesuffix(".SZ")
        return {"akshare": number, "baostock": f"sz.{number}"}
    if code.endswith(".HK"):
        number = code.removesuffix(".HK")
        return {"yfinance": f"{int(number):04d}.HK", "akshare": number}
    if code.startswith("FRED:"):
        return {"fred": code[5:]}
    return {}

def looks_canonical(value: str) -> bool:
    return any(pattern.fullmatch(value) for pattern in CANONICAL_PATTERNS)
