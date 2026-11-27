"""Chart identities and adapters for Alpha pairs and chain-address prices."""
from __future__ import annotations

import asyncio
import math
import time

from app.contracts.chart_workspace import ChartQuote, ChartSymbol
from app.domain.market.candles import candle_end_ms
from app.domain.market.web3_chains import (
    WEB3_CHAIN_BY_ID, WEB3_CHAIN_BY_PLATFORM, is_web3_address, normalize_web3_address,
)
from app.infra.market_data.onchain import OnchainMarketClient

ONCHAIN_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]
CONTRACT_STREAM_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}


class ChartOnchainMarket:
    def __init__(self, client=None, *, cache_service=None):
        self.client = client or OnchainMarketClient(cache_service=cache_service)
        self.registered: dict[str, ChartSymbol] = {}
        self._resolving: dict[str, asyncio.Task] = {}
        self._known_tokens: dict[tuple[str, str], dict] = {}

    @staticmethod
    def _tokens(tokens):
        return [row for row in tokens if row.get("symbol") and row.get("contractAddress")
                and not any(row.get(flag) for flag in ("offline", "fullyDelisted", "cexOffDisplay"))]

    async def alpha_catalog(self):
        tokens, markets = await asyncio.gather(self.client.token_list(), self.client.alpha_markets())
        names = {row["alphaId"]: row for row in self._tokens(tokens) if row.get("alphaId")}
        catalog = {}
        for row in markets:
            token = names.get(row.get("baseAsset"))
            if not token or row.get("status") != "TRADING" or row.get("quoteAsset") != "USDT":
                continue
            filters = {f["filterType"]: f for f in row.get("filters", [])}
            tick = float(filters["PRICE_FILTER"]["tickSize"])
            step = float(filters["LOT_SIZE"]["stepSize"])
            if tick <= 0 or step <= 0:
                continue
            key = f"binance:alpha:{row['symbol']}"
            chain = WEB3_CHAIN_BY_ID.get(str(token.get("chainId")))
            catalog[key] = ChartSymbol(id=key, symbol=row["symbol"], name=f"{token['symbol']}/USDT",
                exchange="binance", market="alpha", currency="USDT", timeframes=ONCHAIN_TIMEFRAMES,
                aliases=[token.get("name", token["symbol"]), token["symbol"], token["contractAddress"],
                         token["alphaId"], chain.label if chain else str(token.get("chainId", ""))],
                metadata={"mintick": tick, "minmove": 1, "pricescale": round(1 / tick), "pointvalue": 1,
                          "mincontract": step, "basecurrency": token["symbol"], "price_basis": "alpha",
                          "chain_id": str(token.get("chainId", "")), "contract_address": token["contractAddress"],
                          "platform": chain.platform if chain else None,
                          "icon_url": token.get("iconUrl"), "asset_name": token.get("name", token["symbol"])})
        return catalog

    @staticmethod
    def _web3_symbol(platform, address, token=None):
        token = token or {}
        chain = WEB3_CHAIN_BY_PLATFORM[platform]
        address = normalize_web3_address(address, platform)
        ticker = token.get("symbol") or f"{address[:6]}…{address[-5:]}"
        key = f"web3:{platform}:{address}"
        return ChartSymbol(id=key, symbol=address, name=f"{ticker}/USD", exchange=platform,
            market="web3", currency="USD", timeframes=ONCHAIN_TIMEFRAMES,
            aliases=[ticker, token.get("name", ticker), address, chain.label],
            metadata={"mintick": 1e-12, "minmove": 1, "pricescale": 10**12, "pointvalue": 1,
                      "mincontract": 1e-8, "basecurrency": ticker, "price_basis": "onchain",
                      "chain_id": chain.chain_id, "platform": platform, "contract_address": address,
                      "icon_url": token.get("iconUrl"), "asset_name": token.get("name", ticker)})

    async def web3_catalog(self):
        catalog = {}
        known = {}
        for token in self._tokens(await self.client.token_list()):
            chain = WEB3_CHAIN_BY_ID.get(str(token.get("chainId")))
            if not chain or not is_web3_address(token["contractAddress"], chain.platform):
                continue
            info = self._web3_symbol(chain.platform, token["contractAddress"], token)
            catalog[info.id] = info
            known[(chain.platform, info.symbol)] = token
        self._known_tokens = known
        return {**self.registered, **catalog}

    async def resolve_web3(self, key):
        parts = key.split(":")
        if len(parts) != 3 or parts[0] != "web3" or parts[1] not in WEB3_CHAIN_BY_PLATFORM:
            raise ValueError("链上品种必须指定受支持的链和合约地址")
        platform, address = parts[1:]
        if not is_web3_address(address, platform):
            raise ValueError("链上合约地址格式无效")
        address = normalize_web3_address(address, platform)
        token = self._known_tokens.get((platform, address))
        info = self._web3_symbol(platform, address, token)
        if token is not None:
            return info
        if info.id in self.registered:
            return self.registered[info.id]
        async def load():
            dynamic = await self.client.web3_dynamic(info.metadata["chain_id"], info.symbol)
            price = float(dynamic.get("price") or 0)
            if not math.isfinite(price) or price <= 0:
                raise ValueError("该链上未找到可用行情")
            rows = await self.history(info, "1h", 1, None, int(time.time() * 1000))
            if not rows:
                raise ValueError("该链上未找到 K 线历史")
            self.registered[info.id] = info
            return info
        task = self._resolving.get(info.id)
        if task is None:
            task = asyncio.create_task(load())
            self._resolving[info.id] = task
            def finished(done):
                self._resolving.pop(info.id, None)
                if not done.cancelled():
                    done.exception()
            task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def search(self, query):
        parts = query.strip().split(":", 1)
        platforms = [parts[0].lower()] if len(parts) == 2 else list(WEB3_CHAIN_BY_PLATFORM)
        address = parts[-1]
        candidates = [platform for platform in platforms if platform in WEB3_CHAIN_BY_PLATFORM
                      and is_web3_address(address, platform)]
        if not candidates:
            raise ValueError("请输入有效的链上合约地址")
        results = await asyncio.gather(*(self.resolve_web3(f"web3:{platform}:{address}")
                                        for platform in candidates), return_exceptions=True)
        found = [result for result in results if isinstance(result, ChartSymbol)]
        errors = [result for result in results if isinstance(result, BaseException) and not isinstance(result, ValueError)]
        if not found and errors:
            raise RuntimeError("链上行情暂时无法读取，请稍后重试") from errors[0]
        return found

    async def history(self, info, timeframe, limit, start, end):
        if start is not None:
            boundary = start
            for _ in range(limit):
                boundary = candle_end_ms(boundary, timeframe)
            end = min(end, boundary - 1)
        try:
            if info.market == "alpha":
                payload = await self.client.alpha_history(info.symbol, timeframe, limit, start, end)
                rows = [[int(row[0]), *map(float, row[1:6])] for row in payload]
            else:
                payload = await self.client.web3_history(info.symbol, info.metadata["platform"], timeframe, limit, start, end)
                rows = [[int(row[5]), *map(float, row[:5])] for row in payload]
            if any(len(row) != 6 for row in rows):
                raise ValueError("incomplete candle")
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError("链上 K 线格式异常") from exc
        if any(not all(math.isfinite(value) for value in row) or row[3] > min(row[1], row[4])
               or max(row[1], row[4]) > row[2] or row[5] < 0 for row in rows):
            raise ValueError("链上 K 线包含无效数据")
        return sorted({row[0]: row for row in rows if row[0] <= end and (start is None or row[0] >= start)}.values())

    async def quote(self, info):
        now = int(time.time() * 1000)
        if info.market == "alpha":
            row = await self.client.alpha_ticker(info.symbol)
            return ChartQuote(id=info.id, price=float(row["lastPrice"]), change=float(row["priceChange"]),
                change_pct=float(row["priceChangePercent"]), updated_at=int(row.get("closeTime") or now))
        row = await self.client.web3_dynamic(info.metadata["chain_id"], info.symbol)
        price = float(row["price"])
        percentage = float(row["percentChange24h"]) if row.get("percentChange24h") is not None else None
        prior = price / (1 + percentage / 100) if percentage is not None and percentage > -100 else None
        return ChartQuote(id=info.id, price=price, change=price - prior if prior is not None else None,
                          change_pct=percentage, updated_at=now)

    @staticmethod
    def stream_url(info, timeframe):
        return ("wss://nbstream.binance.com/w3w/wsa/stream"
                if info.market == "alpha" or timeframe in CONTRACT_STREAM_TIMEFRAMES else None)

    @staticmethod
    def stream_name(info, timeframe):
        if info.market == "alpha":
            return f"{info.symbol.lower()}@kline_{timeframe}"
        return f"came@{info.symbol}@{info.metadata['chain_id']}@kline_{timeframe}"

    async def aclose(self):
        tasks = list(self._resolving.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.client.aclose()
