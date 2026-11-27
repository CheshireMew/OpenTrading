from __future__ import annotations

from dataclasses import dataclass
import re

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
    request_symbol: str | None = None


def parse_market_symbol(value: str, *, default_exchange_id: str) -> MarketSymbolSource | None:
    """Resolve query identity without confusing configured favourites with coverage.

    The exchange adapter verifies listing availability; this boundary validates
    identifiers and keeps spot/perpetual storage and fetch identities distinct.
    """
    value = str(value or "").strip().upper()
    exchange, market, pair = default_exchange_id, "spot", value
    qualified = re.fullmatch(r"(BINANCE|OKX):(SPOT|USDM):([A-Z0-9._/-]+)", value)
    if qualified:
        venue, market, pair = qualified.groups()
        market = market.lower()
        if market == "usdm" and venue != "BINANCE":
            return None
        exchange = "binanceusdm" if market == "usdm" else venue.lower()
        pair = pair.replace("-", "/") if venue == "OKX" else pair
        if "/" not in pair:
            quote = next((q for q in ("USDT", "USDC", "FDUSD", "BTC", "ETH") if pair.endswith(q) and len(pair) > len(q)), None)
            if quote is None:
                return None
            pair = pair[:-len(quote)] + "/" + quote
    elif value.endswith(":PERPETUAL"):
        pair, market, exchange = value.removesuffix(":PERPETUAL"), "usdm", "binanceusdm"
    elif ":" in value:
        # A settlement-qualified perpetual identity must not become a spot key.
        pair, quote = value.rsplit(":", 1)
        if pair.rsplit("/", 1)[-1] != quote:
            return None
        market, exchange = "usdm", "binanceusdm"
    elif re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,39}", pair):
        pair += "/USDT"
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,39}/[A-Z0-9]{2,12}", pair):
        return None
    base, quote = pair.split("/")
    if market == "usdm" or exchange == "binanceusdm":
        return MarketSymbolSource(f"{pair}:{quote}", "binanceusdm", f"binance:usdm:{base}{quote}", f"{pair}:PERPETUAL")
    source = build_market_symbol_source(pair, exchange, default_exchange_id=default_exchange_id)
    request = f"{exchange}:spot:{base + '-' + quote if exchange == 'okx' else base + quote}" if qualified else pair
    return MarketSymbolSource(source.symbol, source.exchange_id, source.storage_symbol, request)


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
