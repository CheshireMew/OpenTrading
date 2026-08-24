from __future__ import annotations

import pytest

from app.services.market.symbol_catalog import get_usd_equivalent_symbols
from app.routers.market import list_market_symbols


@pytest.mark.asyncio
async def test_usd_equivalents_are_searchable_cash_symbols():
    result = await list_market_symbols()
    by_symbol = {item["symbol"]: item for item in result}

    for symbol in ("USD", "USDT", "USDC"):
        assert symbol in get_usd_equivalent_symbols()
        assert by_symbol[symbol]["asset_class"] == "cash"
        assert by_symbol[symbol]["pricing_currency"] == "USD"
