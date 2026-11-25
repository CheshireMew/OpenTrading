from __future__ import annotations

from app.application.errors import InvalidRequestError
from app.domain.market.constants import Timeframe
from app.services.market.symbol_catalog import get_supported_crypto_symbols, get_market_symbol_source

VALID_MARKET_SYMBOLS = get_supported_crypto_symbols()
VALID_MARKET_TIMEFRAMES = [item.value for item in Timeframe]


def validate_market_request(symbol: str, timeframe: str) -> None:
    if get_market_symbol_source(symbol) is None:
        raise InvalidRequestError("无效交易对，请使用 BASE/QUOTE 或交易所市场标识")
    if timeframe not in VALID_MARKET_TIMEFRAMES:
        raise InvalidRequestError(f"无效时间周期。可选: {VALID_MARKET_TIMEFRAMES}")
