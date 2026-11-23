from __future__ import annotations

from typing import Any

from .binance_numbers import safe_float, safe_int


def ticker_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_time": safe_int(event.get("E")),
        "symbol": event.get("s"),
        "price_change": safe_float(event.get("p")),
        "price_change_pct": safe_float(event.get("P")),
        "weighted_avg_price": safe_float(event.get("w")),
        "last_price": safe_float(event.get("c")),
        "last_qty": safe_float(event.get("Q")),
        "open_price": safe_float(event.get("o")),
        "high_price": safe_float(event.get("h")),
        "low_price": safe_float(event.get("l")),
        "volume": safe_float(event.get("v")),
        "quote_volume": safe_float(event.get("q")),
        "open_time": safe_int(event.get("O")),
        "close_time": safe_int(event.get("C")),
        "count": safe_int(event.get("n")),
    }


def mark_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": event.get("s"),
        "pair": None,
        "mark_price": safe_float(event.get("p")),
        "index_price": safe_float(event.get("i")),
        "estimated_settle_price": safe_float(event.get("P")),
        "last_funding_rate": safe_float(event.get("r")),
        "next_funding_time": safe_int(event.get("T")),
        "interest_rate": None,
        "time": safe_int(event.get("E")),
    }
