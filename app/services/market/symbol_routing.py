from __future__ import annotations

from app.services.market.symbol_catalog import get_market_symbol_source
from app.infra.market_data.exchange import ExchangeGateway
from app.domain.market.symbol_catalog import MarketSymbolSource


class MarketSymbolRouting:
    def __init__(self, default_gateway: ExchangeGateway) -> None:
        self.default_gateway = default_gateway
        self._exchange_gateways: dict[str, ExchangeGateway] = {
            default_gateway.exchange_id: default_gateway,
        }

    def storage_symbol(self, symbol: str) -> str:
        source = self._resolve_market_source(symbol)
        return source.storage_symbol if source else symbol

    def fetch_symbol(self, symbol: str) -> str:
        source = self._resolve_market_source(symbol)
        return source.symbol if source else symbol

    def gateway_for_symbol(self, symbol: str) -> ExchangeGateway:
        source = self._resolve_market_source(symbol)
        exchange_id = source.exchange_id if source else self.default_gateway.exchange_id
        gateway = self._exchange_gateways.get(exchange_id)
        if gateway:
            return gateway
        gateway = ExchangeGateway(exchange_id=exchange_id)
        self._exchange_gateways[exchange_id] = gateway
        return gateway

    def _resolve_market_source(self, symbol: str):
        value = symbol.strip().upper()
        if value.endswith(":PERPETUAL"):
            pair = value.removesuffix(":PERPETUAL")
            if "/" not in pair:
                raise ValueError("perpetual symbols must use BASE/QUOTE:PERPETUAL")
            base, quote = pair.split("/", 1)
            return MarketSymbolSource(
                symbol=f"{pair}:{quote}", exchange_id="binanceusdm",
                storage_symbol=f"binance:usdm:{base}{quote}",
            )
        return get_market_symbol_source(symbol) or get_market_symbol_source(f"{symbol}/USDT")
