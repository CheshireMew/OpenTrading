from __future__ import annotations

from dataclasses import dataclass

USD_EQUIVALENT_SYMBOLS = (
    "USD",
    "USDT",
    "USDC",
    "FDUSD",
    "BUSD",
    "DAI",
    "TUSD",
    "USDP",
    "PYUSD",
    "USDS",
)


@dataclass(frozen=True)
class MarketSymbolSource:
    symbol: str
    exchange_id: str
    storage_symbol: str


def normalize_market_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        return ""
    if "/" in symbol:
        return symbol
    return f"{symbol}/USDT"


def build_market_symbol_source(
    symbol: str,
    exchange_id: str,
    *,
    default_exchange_id: str,
) -> MarketSymbolSource:
    normalized_symbol = normalize_market_symbol(symbol)
    storage_symbol = normalized_symbol if exchange_id == default_exchange_id else f"{exchange_id}:{normalized_symbol}"
    return MarketSymbolSource(
        symbol=normalized_symbol,
        exchange_id=exchange_id,
        storage_symbol=storage_symbol,
    )


def build_market_symbol_catalog(
    symbols: tuple[str, ...] | list[str],
    *,
    default_exchange_id: str,
    extra_symbol_exchanges: dict[str, str] | None = None,
) -> dict[str, MarketSymbolSource]:
    catalog: dict[str, MarketSymbolSource] = {}
    for symbol in symbols:
        source = build_market_symbol_source(
            symbol,
            default_exchange_id,
            default_exchange_id=default_exchange_id,
        )
        catalog[source.symbol] = source
    for symbol, exchange_id in (extra_symbol_exchanges or {}).items():
        source = build_market_symbol_source(
            symbol,
            exchange_id,
            default_exchange_id=default_exchange_id,
        )
        catalog[source.symbol] = source
    return catalog


def get_usd_equivalent_symbols() -> list[str]:
    return list(USD_EQUIVALENT_SYMBOLS)


def is_usd_equivalent_symbol(symbol: str) -> bool:
    value = str(symbol or "").strip().upper()
    if not value:
        return False
    base_symbol = value.split("/")[0]
    return base_symbol in USD_EQUIVALENT_SYMBOLS


__all__ = [
    "MarketSymbolSource",
    "build_market_symbol_catalog",
    "build_market_symbol_source",
    "get_usd_equivalent_symbols",
    "is_usd_equivalent_symbol",
    "normalize_market_symbol",
]
