from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
import httpx
import websockets

from app.contracts.chart_workspace import ChartBar, ChartBars, ChartQuote, ChartSymbol
from app.services.market.symbol_catalog import list_market_search_items

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]


def close_boundary(open_time: int, timeframe: str) -> int:
    if timeframe == "1M":
        dt = datetime.fromtimestamp(open_time / 1000, timezone.utc)
        return int(dt.replace(year=dt.year + (dt.month == 12), month=dt.month % 12 + 1, day=1).timestamp() * 1000)
    return open_time + int(timeframe[:-1]) * {"m": 60000, "h": 3600000, "d": 86400000, "w": 604800000}[timeframe[-1]]


class ChartWorkspaceMarket:
    def __init__(self, binance, index):
        self.binance = binance
        self.index = index
        self.http = httpx.AsyncClient(timeout=25)
        self.catalog: dict[str, ChartSymbol] = {}
        self.catalog_at = 0.0
        self.catalog_lock = asyncio.Lock()
        self.channels: dict[tuple[str, str], tuple[asyncio.Task, set[asyncio.Queue]]] = {}
        self.channel_status: dict[tuple[str,str],dict] = {}

    async def symbols(self) -> list[ChartSymbol]:
        if self.catalog and time.time() - self.catalog_at < 600:
            return list(self.catalog.values())
        async with self.catalog_lock:
            if self.catalog and time.time() - self.catalog_at < 600:
                return list(self.catalog.values())
            collected = {}
            async def venue(market):
                loader = self.binance.spot if market == "spot" else self.binance.usdm
                prefix = "/api/v3" if market == "spot" else "/fapi/v1"
                payload = await loader.client.get_json(prefix + "/exchangeInfo", ttl=600)
                for row in payload["symbols"]:
                    if row.get("status") != "TRADING" or row.get("quoteAsset") != "USDT":
                        continue
                    if market == "usdm" and row.get("contractType") != "PERPETUAL":
                        continue
                    filters = {f["filterType"]: f for f in row.get("filters", [])}
                    tick = float(filters["PRICE_FILTER"]["tickSize"])
                    step = float(filters.get("LOT_SIZE", {}).get("stepSize", 1))
                    key = f"binance:{market}:{row['symbol']}"
                    collected[key] = ChartSymbol(id=key, symbol=row["symbol"], name=f"{row['baseAsset']}/USDT",
                        exchange="binance", market=market, currency="USDT", timeframes=TIMEFRAMES,
                        metadata={"mintick": tick, "minmove": 1, "pricescale": round(1/tick), "pointvalue": 1,
                                  "mincontract": step, "basecurrency": row["baseAsset"]})
            outcomes = await asyncio.gather(venue("spot"), venue("usdm"), return_exceptions=True)
            # A failed venue keeps its last verified metadata; never invent a tick size.
            for market, outcome in zip(("spot", "usdm"), outcomes):
                if isinstance(outcome, Exception):
                    collected.update({k:v for k,v in self.catalog.items() if v.exchange == "binance" and v.market == market})
            for row in list_market_search_items():
                if row["asset_class"] == "index":
                    key = f"index:index:{row['symbol']}"
                    collected[key] = ChartSymbol(id=key, symbol=row["symbol"], name=row["name"], exchange=str(row["exchange"]),
                        market="index", currency=row["currency"], timeframes=["1d"], close_only=True,
                        session="regular", metadata={"price_basis": "index", "capability_pending": True})
            try:
                response = await self.http.get("https://www.okx.com/api/v5/public/instruments", params={"instType":"SPOT", "instId":"OKB-USDT"})
                response.raise_for_status()
                row = response.json()["data"][0]
                tick = float(row["tickSz"])
                key = "okx:spot:OKB-USDT"
                collected[key] = ChartSymbol(id=key, symbol="OKB-USDT", name="OKB/USDT", exchange="okx", market="spot",
                    currency="USDT", timeframes=TIMEFRAMES, metadata={"mintick":tick, "minmove":1,
                    "pricescale":round(1/tick), "pointvalue":1, "mincontract":float(row["lotSz"]), "basecurrency":"OKB"})
            except (httpx.HTTPError, KeyError, IndexError, ValueError):
                if "okx:spot:OKB-USDT" in self.catalog:
                    collected["okx:spot:OKB-USDT"] = self.catalog["okx:spot:OKB-USDT"]
            self.catalog = collected
            self.catalog_at = time.time()
            return list(collected.values())

    async def resolve(self, key: str) -> ChartSymbol:
        await self.symbols()
        if key not in self.catalog:
            raise ValueError("品种不可用或交易所元数据尚未加载，请重试")
        return self.catalog[key]

    async def bars(self, key: str, timeframe: str, limit=1000, start=None, end=None) -> ChartBars:
        info = await self.resolve(key)
        if timeframe not in info.timeframes:
            raise ValueError(f"{info.name} 不支持 {timeframe} 周期")
        now = int(time.time()*1000)
        end = min(end if end is not None else now, now)
        rows = []
        source = info.exchange
        if info.market == "index":
            start_day = datetime.fromtimestamp((start or end - limit * 2 * 86400000)/1000, timezone.utc)
            result = await self.index.get_history_async(symbol=info.symbol, timeframe="1d",
                start_date=start_day.strftime("%Y-%m-%d"), end_date=datetime.fromtimestamp(end/1000, timezone.utc).strftime("%Y-%m-%d"))
            rows = [r.as_row() for r in result.data]
            source = result.source
            info = info.model_copy(update={"close_only": result.is_close_only,
                "currency":result.native_currency, "metadata": {"price_basis":result.price_basis, "source":source}})
            self.catalog[key] = info
        elif info.exchange == "binance":
            loader = self.binance.spot if info.market == "spot" else self.binance.usdm
            result = await loader.get_klines(symbol=info.symbol, interval=timeframe,
                limit=min(limit,1000), start_time=start, end_time=end)
            for row in result["items"]:
                rows.append([int(row["open_time"]), *[float(row[k]) for k in ("open","high","low","close","volume")]])
        else:
            tf = {"1h":"1H", "4h":"4H", "1d":"1Dutc", "1w":"1Wutc", "1M":"1Mutc"}.get(timeframe,timeframe)
            # OKX pages backwards. Bound a forward request to its first `limit`
            # candles, then page backwards inside that window before sorting.
            upper = end
            if start is not None:
                boundary = start
                for _ in range(limit):
                    boundary = close_boundary(boundary,timeframe)
                upper = min(upper,boundary-1)
            while len(rows) < limit:
                r = await self.http.get("https://www.okx.com/api/v5/market/history-candles",
                    params={"instId":info.symbol, "bar":tf, "after":upper+1, "limit":min(limit-len(rows),100)})
                r.raise_for_status()
                if r.json().get("code") != "0":
                    raise ValueError("OKX 历史数据暂不可用")
                batch = [[int(item[0]), *map(float,item[1:6])] for item in r.json()["data"]]
                if not batch:
                    break
                rows.extend(batch)
                next_upper = min(item[0] for item in batch)-1
                if next_upper >= upper or (start is not None and next_upper < start):
                    break
                upper = next_upper
        unique = {int(r[0]):r for r in rows if r[0] <= end and (start is None or r[0] >= start)}
        bars = [ChartBar(time=t, open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5],
                closeTime=close_boundary(t,timeframe), closed=close_boundary(t,timeframe) <= now)
                for t,r in sorted(unique.items())][-limit:]
        return ChartBars(symbol=info, timeframe=timeframe, bars=bars, source=source)

    async def quotes(self, keys: list[str]) -> list[ChartQuote]:
        now = int(time.time()*1000)
        await self.symbols()
        batches = {}
        async def batch(market):
            requested = [self.catalog[k].symbol for k in keys if k in self.catalog and self.catalog[k].exchange == "binance" and self.catalog[k].market == market]
            if not requested:
                return
            loader = self.binance.spot if market == "spot" else self.binance.usdm
            prefix = "/api/v3" if market == "spot" else "/fapi/v1"
            try:
                params = {"symbols":json.dumps(requested,separators=(',',':'))} if market == "spot" else {}
                payload = await loader.client.get_json(prefix+"/ticker/24hr",params=params,ttl=5)
                batches[market] = {r["symbol"]:r for r in payload}
            except Exception as exc:
                batches[market] = exc
        await asyncio.gather(batch("spot"),batch("usdm"))
        async def quote(key):
            try:
                info = await self.resolve(key)
                if info.exchange == "binance":
                    rows = batches[info.market]
                    if isinstance(rows,Exception):
                        raise rows
                    r = rows[info.symbol]
                    return ChartQuote(id=key, price=float(r["lastPrice"]), change=float(r["priceChange"]),
                        change_pct=float(r["priceChangePercent"]), updated_at=int(r["closeTime"]))
                if info.exchange == "okx":
                    r = await self.http.get("https://www.okx.com/api/v5/market/ticker", params={"instId":info.symbol})
                    r.raise_for_status()
                    data = r.json()["data"][0]
                    price, prior = float(data["last"]), float(data["open24h"])
                    return ChartQuote(id=key, price=price, change=price-prior, change_pct=(price/prior-1)*100,
                        updated_at=int(data["ts"]))
                data = (await self.bars(key,"1d",limit=2)).bars
                latest, prior = data[-1], data[-2] if len(data)>1 else data[-1]
                return ChartQuote(id=key, price=latest.close, change=latest.close-prior.close,
                    change_pct=(latest.close/prior.close-1)*100, updated_at=latest.time, basis="交易日")
            except Exception as exc:
                return ChartQuote(id=key, updated_at=now, error=str(exc))
        return await asyncio.gather(*(quote(k) for k in keys))

    def subscribe(self, key, timeframe, queue):
        identity = (key,timeframe)
        if identity not in self.channels:
            listeners = set()
            self.channels[identity] = (asyncio.create_task(self._pump(key,timeframe,listeners)), listeners)
        self.channels[identity][1].add(queue)
        if identity in self.channel_status:
            queue.put_nowait(self.channel_status[identity])

    def unsubscribe(self, key, timeframe, queue):
        entry = self.channels.get((key,timeframe))
        if entry:
            entry[1].discard(queue)
            if not entry[1]:
                entry[0].cancel()
                self.channels.pop((key,timeframe),None)
                self.channel_status.pop((key,timeframe),None)

    async def _pump(self, key, timeframe, listeners):
        sequence = 0
        last_open = None
        def emit(kind, **payload):
            nonlocal sequence
            sequence += 1
            message = {"type":kind, "symbol":key, "timeframe":timeframe,"sequence":sequence, **payload}
            if kind == "status":
                self.channel_status[(key,timeframe)] = message
            for q in list(listeners):
                if q.full():
                    q.get_nowait()
                q.put_nowait(message)
        while True:
            try:
                info = await self.resolve(key)
                emit("status", status="connecting" if info.exchange == "binance" else "polling")
                # Heal from the last received bar before resuming native updates.
                cursor = last_open
                while True:
                    data = await self.bars(key,timeframe,limit=1000 if cursor else 2,start=cursor)
                    for bar in data.bars:
                        emit("bar", bar=bar.model_dump())
                        last_open = bar.time
                    if not cursor or len(data.bars)<1000:
                        break
                    cursor = data.bars[-1].closeTime
                if info.exchange != "binance":
                    await asyncio.sleep(60 if info.market == "index" else 5)
                    continue
                # Binance moved USD-M klines to /market in April 2026. The old
                # socket can accept the connection without delivering any bars.
                host = "wss://stream.binance.com:9443/ws" if info.market == "spot" else "wss://fstream.binance.com/market/ws"
                async with websockets.connect(f"{host}/{info.symbol.lower()}@kline_{timeframe}", open_timeout=15, ping_interval=20) as stream:
                    live = False
                    while True:
                        raw = await asyncio.wait_for(stream.recv(),timeout=30)
                        row = json.loads(raw).get("k")
                        if row:
                            if not live:
                                emit("status",status="live")
                                live = True
                            last_open = int(row["t"])
                            emit("bar",bar=ChartBar(time=last_open,open=float(row["o"]), high=float(row["h"]),
                                low=float(row["l"]),close=float(row["c"]),volume=float(row["v"]),
                                closeTime=int(row["T"])+1,closed=bool(row["x"])).model_dump())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                emit("status",status="polling",error=str(exc))
                try:
                    for bar in (await self.bars(key,timeframe,limit=2)).bars:
                        emit("bar",bar=bar.model_dump())
                except Exception:
                    emit("status",status="offline")
                await asyncio.sleep(5)

    async def close(self):
        tasks = [task for task,_ in self.channels.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.channels.clear()
        await self.http.aclose()
