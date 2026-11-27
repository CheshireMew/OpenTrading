from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from app.infra.market_data.chart import ChartMarketClient
from app.infra.market_data.symbol_icons import SymbolIconClient

from app.contracts.chart_workspace import ChartBar, ChartBars, ChartQuote, ChartSymbol
from app.domain.market.index_catalog import INDEX_CATALOG
from app.services.chart_daily_history import daily_chart_symbols
from app.domain.market.candles import candle_end_ms, current_candle_open_ms
from app.domain.market.constants import timeframe_to_milliseconds
from app.domain.market.symbol_catalog import build_market_symbol_source
from app.domain.market.web3_chains import web3_storage_symbol
from app.infra.executor import run_database
from app.services.market.history_range_coordinator import HistoryRangeCoordinator, merge_ohlcv_rows
from config import settings
from app.infra.market_data.exchange import normalize_ohlcv
from utils.logger import logger
from app.services.chart_index_market import ChartIndexMarket
from app.services.chart_index_catalog import index_symbol

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]


def close_boundary(open_time: int, timeframe: str) -> int:
    return candle_end_ms(open_time, timeframe)


class ChartWorkspaceMarket:
    def __init__(self, binance, index, *, kline_store=None, daily_history=None, onchain=None):
        self.binance = binance
        self.index = index
        self.daily_history = daily_history
        self.onchain = onchain
        self.indices = ChartIndexMarket(index, kline_store)
        self.kline_store = kline_store
        self.http = ChartMarketClient()
        self.icons = SymbolIconClient()
        self.history_ranges = HistoryRangeCoordinator(kline_store, storage_runner=run_database) if kline_store else None
        self.catalog: dict[str, ChartSymbol] = {}
        self.catalog_at = 0.0
        self._static_catalog_ready = False
        self._catalog_checked: dict[str, tuple[float, bool]] = {}
        self._catalog_tasks: dict[str, asyncio.Task] = {}
        self._closed = False
        self.channels: dict[tuple[str, str], tuple[asyncio.Task, set[asyncio.Queue]]] = {}
        self.channel_status: dict[tuple[str,str],dict] = {}
        self.replay_requests: dict[tuple, asyncio.Task] = {}

    async def replay_bars(self, key, timeframe, limit, start, end):
        """Share concurrent public history reads; personal replay stays in the browser."""
        identity = (key, timeframe, limit, start, end)
        task = self.replay_requests.get(identity)
        if task is None:
            async def load():
                result = await self.bars(key, timeframe, limit, start, end - 1)
                return result.model_copy(update={"bars": [bar for bar in result.bars if bar.closed and bar.closeTime <= end]})
            task = asyncio.create_task(load())
            self.replay_requests[identity] = task
            def finished(completed):
                self.replay_requests.pop(identity, None)
                if not completed.cancelled():
                    completed.exception()
            task.add_done_callback(finished)
        return await asyncio.shield(task)

    def _static_symbols(self):
        if self._static_catalog_ready:
            return
        self._static_catalog_ready = True
        for symbol in INDEX_CATALOG:
            info = index_symbol(symbol)
            self.catalog.setdefault(info.id, info)
        if self.daily_history is not None:
            for item in daily_chart_symbols():
                self.catalog.setdefault(item.id, item)

    def _refresh_catalogs(self):
        self._static_symbols()
        if self._closed:
            return
        now = time.time()
        # Explicitly injected verified catalogs retain the same TTL as before.
        if not self._catalog_checked and self.catalog_at and now - self.catalog_at < 600:
            return
        venues = ("binance:spot", "binance:usdm", "okx:spot") + (("binance:alpha", "web3") if self.onchain else ())
        for venue in venues:
            checked, success = self._catalog_checked.get(venue, (0, False))
            if venue in self._catalog_tasks or now - checked < (600 if success else 30):
                continue
            task = asyncio.create_task(self._load_catalog(venue), name=f"chart-symbols:{venue}")
            self._catalog_tasks[venue] = task
            def finished(completed, identity=venue):
                if self._catalog_tasks.get(identity) is completed:
                    self._catalog_tasks.pop(identity, None)
                if not completed.cancelled():
                    completed.exception()
            task.add_done_callback(finished)

    async def _load_catalog(self, venue):
        try:
            collected = {}
            if venue == "binance:alpha":
                collected = await self.onchain.alpha_catalog()
            elif venue == "web3":
                collected = await self.onchain.web3_catalog()
            elif venue.startswith("binance:"):
                market = venue.split(":")[1]
                loader = self.binance.spot if market == "spot" else self.binance.usdm
                prefix = "/api/v3" if market == "spot" else "/fapi/v1"
                payload = await loader.client.get_json(prefix + "/exchangeInfo", ttl=600)
                for row in payload["symbols"]:
                    if row.get("status") != "TRADING" or row.get("quoteAsset") != "USDT":
                        continue
                    if market == "usdm" and row.get("contractType") not in {"PERPETUAL", "TRADIFI_PERPETUAL"}:
                        continue
                    filters = {f["filterType"]: f for f in row.get("filters", [])}
                    tick = float(filters["PRICE_FILTER"]["tickSize"])
                    step = float(filters.get("LOT_SIZE", {}).get("stepSize", 1))
                    key = f"binance:{market}:{row['symbol']}"
                    collected[key] = ChartSymbol(id=key, symbol=row["symbol"], name=f"{row['baseAsset']}/USDT",
                        exchange="binance", market=market, currency="USDT", timeframes=TIMEFRAMES,
                        metadata={"mintick":tick, "minmove":1, "pricescale":round(1/tick), "pointvalue":1,
                                  "mincontract":step, "basecurrency":row["baseAsset"]})
            else:
                row = await self.http.okx_symbol("OKB-USDT")
                tick = float(row["tickSz"])
                key = "okx:spot:OKB-USDT"
                collected[key] = ChartSymbol(id=key, symbol="OKB-USDT", name="OKB/USDT", exchange="okx", market="spot",
                    currency="USDT", timeframes=TIMEFRAMES, metadata={"mintick":tick, "minmove":1,
                    "pricescale":round(1/tick), "pointvalue":1, "mincontract":float(row["lotSz"]), "basecurrency":"OKB"})
            self.catalog = {**{key:info for key,info in self.catalog.items() if not key.startswith(venue + ":")}, **collected}
            self.catalog_at = time.time()
            self._catalog_checked[venue] = (self.catalog_at, True)
        except Exception as exc:
            # A failure retains only this venue's last verified metadata. Other
            # venues publish independently and never wait behind its timeout.
            self._catalog_checked[venue] = (time.time(), False)
            logger.warning("Chart symbol catalog %s unavailable: %s", venue, type(exc).__name__)

    async def symbols(self, *, wait_for_refresh: bool = False) -> list[ChartSymbol]:
        self._refresh_catalogs()
        pending = set(self._catalog_tasks.values())
        if wait_for_refresh:
            # Background browser refreshes need the completed snapshot. A
            # cancelled visitor must not cancel shared exchange acquisition.
            await asyncio.gather(*(asyncio.shield(task) for task in pending))
        while pending and not any(info.market in {"spot", "usdm", "alpha", "web3"} for info in self.catalog.values()):
            _, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        return list(self.catalog.values())

    async def resolve(self, key: str) -> ChartSymbol:
        self._refresh_catalogs()
        if key not in self.catalog:
            venue = "web3" if key.startswith("web3:") else ":".join(key.split(":")[:2])
            task = self._catalog_tasks.get(venue)
            if task is not None:
                await asyncio.shield(task)
        if key not in self.catalog and self.onchain is not None and key.startswith("web3:"):
            info = await self.onchain.resolve_web3(key)
            self.catalog[info.id] = info
            return info
        if key not in self.catalog:
            raise ValueError("品种不可用或交易所元数据尚未加载，请重试")
        return self.catalog[key]

    async def search_symbols(self, query: str) -> list[ChartSymbol]:
        if self.onchain is None:
            raise ValueError("链上行情服务尚未就绪")
        found = await self.onchain.search(query)
        self.catalog.update({info.id: info for info in found})
        return found

    async def bars(self, key: str, timeframe: str, limit=1000, start=None, end=None) -> ChartBars:
        info = await self.resolve(key)
        if timeframe not in info.timeframes:
            raise ValueError(f"{info.name} 不支持 {timeframe} 周期")
        now = int(time.time()*1000)
        end = min(end if end is not None else now, now)
        if info.market == "index":
            return await self.indices.bars(info.symbol, timeframe, limit, start, end)
        rows = []
        source = "binance-alpha" if info.market == "alpha" else "binance-web3" if info.market == "web3" else info.exchange
        if info.market in {"fx", "commodity"}:
            span = max(limit * 2, 14) * 86400000
            lower = start if start is not None else end - span
            upper = min(end, lower + span) if start is not None else end
            start_day = datetime.fromtimestamp(lower / 1000, timezone.utc).date()
            end_day = min(datetime.fromtimestamp(upper / 1000, timezone.utc).date(),
                          datetime.fromtimestamp(now / 1000, timezone.utc).date() - timedelta(days=1))
            if start_day > end_day:
                return ChartBars(symbol=info, timeframe=timeframe, bars=[], source=source)
        if info.market in {"fx", "commodity"}:
            if self.daily_history is None:
                raise ValueError("日线行情服务尚未就绪")
            snapshot = await self.daily_history.snapshot(info.symbol, start_day, end_day)
            rows = [[int(bar.observed_at.timestamp() * 1000), bar.open, bar.high, bar.low, bar.close,
                     bar.volume or 0.0] for bar in snapshot.bars]
            source = snapshot.provider
            info = info.model_copy(update={"close_only": False,
                "metadata": {**info.metadata, "source": source, "snapshot_hash": snapshot.snapshot_hash}})
            self.catalog[key] = info
        elif info.market == "web3":
            rows = await self._web3_bars(info, timeframe, limit, start, end, now)
        else:
            rows = (await self._shared_crypto_bars(info, timeframe, limit, start, end, now)
                    if self.history_ranges is not None
                    else await self._fetch_crypto_rows(info, timeframe, limit, start, end))
        unique = {int(r[0]):r for r in rows if r[0] <= end and (start is None or r[0] >= start)}
        ordered = sorted(unique.items())
        selected = ordered[:limit] if start is not None else ordered[-limit:]
        bars = [ChartBar(time=t, open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5],
                closeTime=close_boundary(t,timeframe), closed=close_boundary(t,timeframe) <= now)
                for t,r in selected]
        return ChartBars(symbol=info, timeframe=timeframe, bars=bars, source=source)

    async def _web3_bars(self, info, timeframe, limit, start, end, now):
        # Chain candles can be sparse. A request for the latest N trades must
        # not become a request for N consecutive periods ending at the clock.
        storage = self._storage_symbol(info)
        # N cached rows do not prove completeness for a sparse source. The
        # upstream client caches exact historical pages, including their gaps.
        rows = await self.onchain.history(info, timeframe, limit, start, end)
        confirmed = [row for row in rows if candle_end_ms(int(row[0]), timeframe) <= now]
        if confirmed and self.kline_store is not None:
            await run_database(lambda: self.kline_store.save(storage, timeframe, confirmed))
        return rows

    async def _fetch_crypto_rows(self, info, timeframe, limit, start, end):
        rows = []
        if info.market in {"alpha", "web3"}:
            return await self.onchain.history(info, timeframe, limit, start, end)
        if info.exchange == "binance":
            loader = self.binance.spot if info.market == "spot" else self.binance.usdm
            prefix = "/api/v3" if info.market == "spot" else "/fapi/v1"
            params = {"symbol": info.symbol, "interval": timeframe, "limit": min(limit, 1000)}
            if start is not None:
                params["startTime"] = start
            if end is not None:
                params["endTime"] = end
            # The chart range coordinator already owns persistence. Reading the
            # raw endpoint avoids a second normalized history copy and prevents
            # a partial research-store fallback from looking like empty history.
            rows = normalize_ohlcv(await loader.client.get_json(prefix + "/klines", params=params))
        else:
            rows = await self.http.okx_history(info.symbol, timeframe, limit, start, end)
        return rows

    @staticmethod
    def _storage_symbol(info):
        if info.market == "alpha":
            return info.id
        if info.market == "web3":
            return web3_storage_symbol(info.symbol, info.metadata["platform"])
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
        needs_live = start <= current_open < upper and current_open <= end
        live = None

        async def fetch_gap(since, until):
            nonlocal live
            output = []
            while since < until:
                # A cold recent page includes its forming candle in the same
                # venue request. Only confirmed rows enter shared persistence.
                include_live = needs_live and until == current_open
                batch = await self._fetch_crypto_rows(info, timeframe, min(limit, 1000), since,
                                                      end if include_live else until - 1)
                if include_live:
                    live = [row for row in batch if int(row[0]) == current_open]
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
        if needs_live and live is None:
            live = await self._fetch_crypto_rows(info, timeframe, 1, current_open, end)
        return merge_ohlcv_rows(result.rows, live or [], start_ts=start, end_ts_exclusive=min(upper, end + 1))

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
                if info.market == "index":
                    return await self.indices.quote(info.symbol)
                if info.market in {"alpha", "web3"}:
                    return await self.onchain.quote(info)
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
                if info.market in {"alpha", "web3"}:
                    stream_url = self.onchain.stream_url(info, timeframe)
                elif info.exchange == "binance":
                    host = "wss://stream.binance.com:9443/ws" if info.market == "spot" else "wss://fstream.binance.com/market/ws"
                    stream_url = f"{host}/{info.symbol.lower()}@kline_{timeframe}"
                else:
                    stream_url = None
                emit("status", status="connecting" if stream_url else "delayed" if info.metadata.get("data_status") == "delayed" else "polling")
                # Heal from the last received bar before resuming native updates.
                cursor = last_open
                while True:
                    data = await self.bars(key,timeframe,limit=1000 if cursor else 2,start=cursor)
                    for bar in data.bars:
                        polling_quote = not stream_url and info.metadata.get("data_status") != "delayed" and bar is data.bars[-1]
                        emit("bar", live=polling_quote,
                             observed_at=(bar.closeTime if bar.closed else int(time.time() * 1000)) if polling_quote else None,
                             bar=bar.model_dump())
                        last_open = bar.time
                    if not cursor or len(data.bars)<1000:
                        break
                    cursor = data.bars[-1].closeTime
                if not stream_url:
                    await asyncio.sleep(60 if info.market in {"index", "fx", "commodity"} else 5)
                    continue
                # Binance moved USD-M klines to /market in April 2026. The old
                # socket can accept the connection without delivering any bars.
                async with self.http.websocket(stream_url) as stream:
                    if info.market in {"alpha", "web3"}:
                        await stream.send(json.dumps({"method": "SUBSCRIBE",
                            "params": [self.onchain.stream_name(info, timeframe)], "id": 1}))
                    live = False
                    while True:
                        raw = await asyncio.wait_for(stream.recv(),timeout=30)
                        event = json.loads(raw)
                        event = event.get("data", event)
                        row = event.get("k")
                        if row:
                            if not live:
                                emit("status",status="live")
                                live = True
                            last_open = int(row["ot"] if "ot" in row else row["t"])
                            close_time = int(row["ct"]) if "ct" in row else int(row["T"]) + 1
                            observed_at = int(event.get("E") or time.time() * 1000)
                            emit("bar",live=True,observed_at=observed_at,bar=ChartBar(time=last_open,open=float(row["o"]), high=float(row["h"]),
                                low=float(row["l"]),close=float(row["c"]),volume=float(row["v"]),
                                closeTime=close_time,closed=bool(row.get("x", close_time <= observed_at))).model_dump())
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
        self._closed = True
        tasks = ([task for task,_ in self.channels.values()] + list(self.replay_requests.values())
                 + list(self._catalog_tasks.values()))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.channels.clear()
        await self.indices.close()
        if self.daily_history is not None:
            await self.daily_history.close()
        if self.onchain is not None:
            await self.onchain.aclose()
        await self.icons.aclose()
        await self.http.aclose()
