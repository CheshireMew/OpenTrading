from __future__ import annotations

from typing import Any

from .binance_numbers import to_float


def normalize_quote_asset(value: str | None) -> str:
    return str(value or "USDT").strip().upper()


def collect_spot_candidates(
    rows: list[dict[str, Any]],
    *,
    min_rise_pct: float,
    quote_asset: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in rows:
        symbol = str(item.get("symbol") or "").upper()
        change_pct = to_float(item.get("price_change_pct"))
        if not is_watchable_symbol("spot", symbol, quote_asset):
            continue
        if change_pct is None or change_pct < min_rise_pct:
            continue
        candidates.append({
            "market": "spot",
            "market_label": "现货",
            "symbol": symbol,
            "last_price": to_float(item.get("last_price")),
            "mark_price": None,
            "price_change_pct": change_pct,
            "quote_volume": to_float(item.get("quote_volume")),
            "funding_rate_pct": None,
        })
    return candidates


def collect_derivatives_candidates(
    market: str,
    ticker_rows: list[dict[str, Any]],
    mark_rows: list[dict[str, Any]],
    *,
    min_rise_pct: float,
    quote_asset: str,
) -> list[dict[str, Any]]:
    mark_map = {str(item.get("symbol") or "").upper(): item for item in mark_rows}
    candidates: list[dict[str, Any]] = []
    for item in ticker_rows:
        symbol = str(item.get("symbol") or "").upper()
        change_pct = to_float(item.get("price_change_pct"))
        if not is_watchable_symbol(market, symbol, quote_asset) or change_pct is None or change_pct < min_rise_pct:
            continue
        mark = mark_map.get(symbol, {})
        funding_rate = to_float(mark.get("last_funding_rate"))
        candidates.append({
            "market": market,
            "market_label": "U 本位" if market == "usdm" else "币本位",
            "symbol": symbol,
            "last_price": to_float(item.get("last_price")),
            "mark_price": to_float(mark.get("mark_price")),
            "price_change_pct": change_pct,
            "quote_volume": to_float(item.get("quote_volume")),
            "funding_rate_pct": funding_rate * 100.0 if funding_rate is not None else None,
        })
    return candidates


def is_watchable_symbol(market: str, symbol: str, quote_asset: str) -> bool:
    normalized = str(symbol or "").upper()
    if market == "spot":
        if not normalized.endswith(quote_asset):
            return False
        base_symbol = normalized[: -len(quote_asset)]
        leveraged_suffixes = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "4L", "4S", "5L", "5S")
        return bool(base_symbol) and not base_symbol.endswith(leveraged_suffixes)
    if market == "usdm":
        return normalized.endswith(quote_asset) and "_" not in normalized
    return normalized.endswith("_PERP")
