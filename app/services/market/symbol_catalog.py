from __future__ import annotations

from app.domain.market.index_catalog import INDEX_CATALOG, get_index_instrument
from app.domain.market.symbol_catalog import (
    MarketSymbolSource,
    build_market_symbol_catalog,
    get_usd_equivalent_symbols,
    is_usd_equivalent_symbol,
    normalize_market_symbol,
)
from config import settings


EXTRA_MARKET_SYMBOL_EXCHANGES: dict[str, str] = {
    "BNB/USDT": settings.EXCHANGE_ID,
    "PAXG/USDT": settings.EXCHANGE_ID,
    "ZEC/USDT": settings.EXCHANGE_ID,
    "OKB/USDT": "okx",
}

MARKET_SYMBOL_CATALOG = build_market_symbol_catalog(
    settings.SYMBOLS,
    default_exchange_id=settings.EXCHANGE_ID,
    extra_symbol_exchanges=EXTRA_MARKET_SYMBOL_EXCHANGES,
)


def get_supported_crypto_symbols() -> list[str]:
    return list(MARKET_SYMBOL_CATALOG)


def get_supported_market_symbols() -> list[str]:
    return get_supported_crypto_symbols()


def get_market_symbol_source(symbol: str) -> MarketSymbolSource | None:
    normalized_symbol = normalize_market_symbol(symbol)
    if not normalized_symbol:
        return None
    return MARKET_SYMBOL_CATALOG.get(normalized_symbol)


def list_market_search_items() -> list[dict[str, object]]:
    cash_symbols = [
        {
            "symbol": symbol,
            "name": "US Dollar" if symbol == "USD" else f"{symbol} USD equivalent",
            "asset_class": "cash",
            "market": "USD",
            "currency": "USD",
            "exchange": "USD",
            "aliases": ["美元", "现金", "stablecoin", "稳定币", "usd equivalent"],
            "pricing_symbol": None,
            "pricing_name": None,
            "pricing_currency": "USD",
        }
        for symbol in get_usd_equivalent_symbols()
    ]
    crypto_symbols = [
        {
            "symbol": source.symbol,
            "name": source.symbol,
            "asset_class": "crypto",
            "market": "CRYPTO",
            "currency": "USDT",
            "exchange": source.exchange_id.upper(),
            "aliases": [source.symbol.split("/")[0]],
            "pricing_symbol": None,
            "pricing_name": None,
            "pricing_currency": "USDT",
        }
        for source in MARKET_SYMBOL_CATALOG.values()
    ]
    index_symbols = [
        {
            "symbol": instrument.symbol,
            "name": instrument.name,
            "asset_class": "index",
            "market": instrument.market,
            "currency": instrument.currency,
            "exchange": instrument.market,
            "aliases": list(instrument.aliases),
            "pricing_symbol": instrument.pricing_symbol,
            "pricing_name": instrument.pricing_name,
            "pricing_currency": instrument.pricing_currency or instrument.currency,
        }
        for instrument in INDEX_CATALOG.values()
    ]
    return cash_symbols + crypto_symbols + index_symbols


def resolve_market_asset(symbol: str) -> dict[str, str] | None:
    value = str(symbol or "").strip().upper()
    if not value:
        return None
    if is_usd_equivalent_symbol(value):
        return {"symbol": value.split("/")[0], "asset_class": "cash"}

    instrument = get_index_instrument(value)
    if instrument:
        return {"symbol": instrument.symbol, "asset_class": "index"}

    source = get_market_symbol_source(value)
    if source:
        return {"symbol": source.symbol, "asset_class": "crypto"}
    return None


__all__ = [
    "MARKET_SYMBOL_CATALOG",
    "MarketSymbolSource",
    "get_market_symbol_source",
    "get_supported_crypto_symbols",
    "get_supported_market_symbols",
    "get_usd_equivalent_symbols",
    "is_usd_equivalent_symbol",
    "list_market_search_items",
    "normalize_market_symbol",
    "resolve_market_asset",
]
