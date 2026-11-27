"""Public Alpha and Binance Wallet market endpoints; no account access."""
from __future__ import annotations

import asyncio
import time

from app.domain.market.candles import candle_end_ms, current_candle_open_ms
from app.infra.market_data.binance_api import BinanceApiSupport, compact_query
from config import settings


class OnchainMarketClient:
    def __init__(self, *, cache_service=None):
        self.alpha = BinanceApiSupport(base_url="https://www.binance.com",
            cache_namespace="chart:alpha", cache_service=cache_service)
        self.wallet = BinanceApiSupport(base_url=settings.BINANCE_WEB3_BASE_URL,
            cache_namespace="binance:web3", cache_service=cache_service)
        self.candles = BinanceApiSupport(base_url=settings.BINANCE_WEB3_KLINE_BASE_URL,
            cache_namespace="binance:web3:kline", cache_service=cache_service)

    @staticmethod
    def _data(payload):
        if payload.get("success") is False or payload.get("code") not in {None, 0, "0", "000000"}:
            raise RuntimeError("链上行情来源暂时不可用")
        return payload.get("data")

    async def token_list(self):
        data = self._data(await self.alpha.get_json(
            "/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list", ttl=600))
        if not isinstance(data, list):
            raise ValueError("链上品种目录格式异常")
        return data

    async def alpha_markets(self):
        data = self._data(await self.alpha.get_json("/bapi/defi/v1/public/alpha-trade/get-exchange-info", ttl=600))
        if not isinstance(data, dict) or not isinstance(data.get("symbols"), list):
            raise ValueError("Alpha 品种目录格式异常")
        return data["symbols"]

    async def alpha_history(self, symbol, timeframe, limit, start, end):
        data = self._data(await self.alpha.get_json("/bapi/defi/v1/public/alpha-trade/klines",
            params=compact_query({"symbol": symbol, "interval": timeframe, "limit": limit,
                                  "startTime": start, "endTime": end}), ttl=5))
        if not isinstance(data, list):
            raise ValueError("Alpha K 线格式异常")
        return data

    async def alpha_ticker(self, symbol):
        data = self._data(await self.alpha.get_json("/bapi/defi/v1/public/alpha-trade/ticker",
            params={"symbol": symbol}, ttl=5))
        if not isinstance(data, dict):
            raise ValueError("Alpha 报价格式异常")
        return data

    async def web3_dynamic(self, chain_id, address):
        data = self._data(await self.wallet.get_json(
            "/bapi/defi/v4/public/wallet-direct/buw/wallet/market/token/dynamic/info/ai",
            params={"chainId": chain_id, "contractAddress": address}, ttl=5))
        return data if isinstance(data, dict) else {}

    async def web3_history(self, address, platform, timeframe, limit, start, end):
        interval = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min"}.get(timeframe, timeframe)
        historical = candle_end_ms(current_candle_open_ms(end, timeframe), timeframe) <= int(time.time() * 1000)
        data = self._data(await self.candles.get_json("/u-kline/v1/k-line/candles",
            params=compact_query({"address": address, "platform": platform, "interval": interval,
                                  "limit": limit, "from": start, "to": end, "pm": "p"}),
            ttl=86400 if historical else 5))
        if not isinstance(data, list):
            raise ValueError("链上 K 线格式异常")
        return data

    async def aclose(self):
        await asyncio.gather(self.alpha.aclose(), self.wallet.aclose(), self.candles.aclose())
