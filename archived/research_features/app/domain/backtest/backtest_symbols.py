from __future__ import annotations

import re

from app.domain.market.symbol_catalog import get_market_symbol_source, normalize_market_symbol


def normalize_backtest_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    for symbol in symbols:
        value = normalize_market_symbol(symbol)
        source = get_market_symbol_source(value)
        if source is None:
            raise ValueError(f"回测不支持的交易对: {symbol}")
        if source.symbol not in normalized:
            normalized.append(source.symbol)
    if not normalized:
        raise ValueError("至少需要一个交易对")
    return normalized


def sanitize_backtest_run_fragment(value: str) -> str:
    fragment = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    fragment = fragment.strip("._-")
    if not fragment:
        raise ValueError("回测运行目录片段为空")
    return fragment[:96]
