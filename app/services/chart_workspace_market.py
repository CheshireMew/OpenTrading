from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from app.infra.market_data.chart import ChartMarketClient, MarketHttpError

from app.contracts.chart_workspace import ChartBar, ChartBars, ChartQuote, ChartSymbol
from app.services.market.symbol_catalog import list_market_search_items
from app.domain.market.candles import candle_end_ms, current_candle_open_ms
from app.domain.market.constants import timeframe_to_milliseconds
from app.domain.market.symbol_catalog import build_market_symbol_source
from app.infra.executor import run_database
from app.services.market.history_range_coordinator import HistoryRangeCoordinator, merge_ohlcv_rows
from config import settings

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]


def close_boundary(open_time: int, timeframe: str) -> int:
    return candle_end_ms(open_time, timeframe)


class ChartWorkspaceMarket:
    def __init__(self, binance, index, *, kline_store=None):
        self.binance = binance
        self.index = index
        self.http = ChartMarketClient()
        self.history_ranges = HistoryRangeCoordinator(kline_store, storage_runner=run_database) if kline_store else None
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
                row = await self.http.okx_symbol("OKB-USDT")
                tick = float(row["tickSz"])
                key = "okx:spot:OKB-USDT"
                collected[key] = ChartSymbol(id=key, symbol="OKB-USDT", name="OKB/USDT", exchange="okx", market="spot",
                    currency="USDT", timeframes=TIMEFRAMES, metadata={"mintick":tick, "minmove":1,
                    "pricescale":round(1/tick), "pointvalue":1, "mincontract":float(row["lotSz"]), "basecurrency":"OKB"})
            except (MarketHttpError, KeyError, IndexError, ValueError):
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
        else:
            rows = (await self._shared_crypto_bars(info, timeframe, limit, start, end, now)
                    if self.history_ranges is not None
                    else await self._fetch_crypto_rows(info, timeframe, limit, start, end))
        unique = {int(r[0]):r for r in rows if r[0] <= end and (start is None or r[0] >= start)}
        bars = [ChartBar(time=t, open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5],
                closeTime=close_boundary(t,timeframe), closed=close_boundary(t,timeframe) <= now)
                for t,r in sorted(unique.items())][-limit:]
        return ChartBars(symbol=info, timeframe=timeframe, bars=bars, source=source)

    async def _fetch_crypto_rows(self, info, timeframe, limit, start, end):
        rows = []
        if info.exchange == "binance":
            loader = self.binance.spot if info.market == "spot" else self.binance.usdm
            result = await loader.get_klines(symbol=info.symbol, interval=timeframe,
                limit=min(limit,1000), start_time=start, end_time=end)
            for row in result["items"]:
                rows.append([int(row["open_time"]), *[float(row[k]) for k in ("open","high","low","close","volume")]])
        else:
            rows = await self.http.okx_history(info.symbol, timeframe, limit, start, end)
        return rows

    @staticmethod
    def _storage_symbol(info):
        if info.market == "usdm":
            return f"{info.exchange}:usdm:{info.symbol}"
        pair = (info.symbol.replace("-", "/") if "-" in info.symbol
                else f"{info.symbol.removesuffix(info.currency)}/{info.currency}")
        return build_market_symbol_source(pair, info.exchange, default_exchange_id=settings.EXCHANGE_ID).storage_symbol

    async def _shared_crypto_bars(self, info, timeframe, limit, start, end, now):
        if limit < 1:
            return []
        final_open = current_candle_open_ms(end, timeframe)
        if start is None:
            if timeframe.endswith("M"):
                anchor = datetime.fromtimestamp(final_open / 1000, timezone.utc)
                month = anchor.year * 12 + anchor.month - limit
                start = int(anchor.replace(year=month // 12, month=month % 12 + 1).timestamp() * 1000)
            else:
                start = final_open - (limit - 1) * timeframe_to_milliseconds(timeframe)
        else:
            aligned = current_candle_open_ms(start, timeframe)
            start = aligned if aligned == start else candle_end_ms(aligned, timeframe)
        upper = start
        for _ in range(limit):
            upper = candle_end_ms(upper, timeframe)
        upper = min(upper, candle_end_ms(final_open, timeframe))
        current_open = current_candle_open_ms(now, timeframe)
        closed_upper = min(upper, current_open)

        async def fetch_gap(since, until):
            output = []
            while since < until:
                batch = await self._fetch_crypto_rows(info, timeframe, min(limit, 1000), since, until - 1)
                batch = [row for row in batch if since <= int(row[0]) < until]
                if not batch:
                    break
                output.extend(batch)
                following = candle_end_ms(max(int(row[0]) for row in batch), timeframe)
                if following <= since:
                    break
                since = following
            return output

        result = await self.history_ranges.load_async(
            storage_symbol=self._storage_symbol(info), timeframe=timeframe,
            start_ts=start, end_ts_exclusive=closed_upper, fetch_gap=fetch_gap,
        )
        live = []
        if start <= current_open < upper and current_open <= end:
            live = await self._fetch_crypto_rows(info, timeframe, 1, current_open, end)
        return merge_ohlcv_rows(result.rows, live, start_ts=start, end_ts_exclusive=min(upper, end + 1))

    async def quotes(self, keys: list[str]) -> list[ChartQuote]:
        now = int(time.time()*1000)
        await self.symbols()
        batches = {}
        if settings.PUBLIC_SITE:
            # Reuse the shared live market feed, independent of each visitor's
            # watchlist. Do not issue another exchange request per watchlist.
            snapshot = await self.binance.snapshot_service.get_market_page_snapshot_data()
            for market in ("spot", "usdm"):
                batches[market] = {row["symbol"]: {"symbol": row["symbol"], "lastPrice": row.get("last_price"),
                    "priceChange": row.get("price_change"), "priceChangePercent": row.get("price_change_pct"),
                    "closeTime": row.get("close_time") or snapshot.get("updated_at") or now}
                    for row in snapshot.get(market + "_ticker", {}).get("items", [])}
        async def batch(market):
            if settings.PUBLIC_SITE:
                return
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
                    data = await self.http.okx_ticker(info.symbol)
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
            if settings.PUBLIC_SITE and len(self.channels) >= 32:
                raise ValueError("实时行情连接已满，请稍后重试")
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
                async with self.http.websocket(f"{host}/{info.symbol.lower()}@kline_{timeframe}") as stream:
                    live = False
                    while True:
                        raw = await asyncio.wait_for(stream.recv(),timeout=30)
                        row = json.loads(raw).get("k")
                        if row:
                            if not live:
                                emit("status",status="live")
                                live = True
                            last_open = int(row["t"])
                            emit("bar",live=True,bar=ChartBar(time=last_open,open=float(row["o"]), high=float(row["h"]),
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
