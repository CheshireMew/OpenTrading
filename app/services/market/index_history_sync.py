"""Persist published index observations from the existing free feeds."""
import time

from app.domain.market.candles import candle_end_ms
from app.domain.market.index_catalog import INDEX_CATALOG
from app.domain.market.index_history_policy import full_index_row, live_index_rows, live_start_ms, utc_datetime
from app.infra.market_calendar import session_dates
from app.infra.market_data.index_chart import IndexChartClient
from app.infra.persistence.market.kline_store import KlineStore
from app.services.chart_index_catalog import PERIODS, RETENTION, index_symbol
from app.services.chart_index_market import aggregate, period_open, DAY
from app.services.market.index_history_sources import IndexHistorySources


class IndexHistorySync:
    def __init__(self, database=None, *, store=None, client=None, sources=None, progress=None):
        self.store = store if store is not None else KlineStore(database_runtime=database)
        self.client = client or IndexChartClient()
        self.sources = sources or IndexHistorySources()
        self.progress = progress or (lambda _: None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def _save(self, instrument, timeframe, rows, start, end):
        rows = [row for row in live_index_rows(instrument, rows) if start <= row[0] and
            candle_end_ms(int(row[0]), timeframe) <= end]
        if not rows:
            return 0, 0
        known = {row[0]: row for row in self.store.get_range(instrument.storage_symbol, timeframe,
            min(row[0] for row in rows), max(row[0] for row in rows))}
        # A fallback must never replace an existing real OHLC candle with a
        # close-only value. Repair missing OHLC, otherwise preserve saved bars.
        pending = {row[0]: row for row in rows if row[0] not in known or
            (not full_index_row(known[row[0]]) and full_index_row(row))}
        added = sum(stamp not in known for stamp in pending)
        repaired = len(pending) - added
        pending = list(pending.values())
        for offset in range(0, len(pending), 2000):
            self.store.save(instrument.storage_symbol, timeframe, pending[offset:offset+2000])
        return added, repaired

    def sync(self, symbol, *, timeframes=None, start=None, end=None):
        if symbol not in INDEX_CATALOG:
            raise ValueError(f"Unknown index: {symbol}")
        wanted = set(timeframes or PERIODS)
        if wanted - set(PERIODS):
            raise ValueError(f"Unsupported index periods: {sorted(wanted-set(PERIODS))}")
        instrument = INDEX_CATALOG[symbol]
        now = int(time.time()*1000)
        until = min(int(end.timestamp()*1000) if end else now, now)
        since = max(int(start.timestamp()*1000) if start else live_start_ms(instrument), live_start_ms(instrument))
        result = {"symbol":symbol,"history_policy":"live-only","launch_date":instrument.launch_date,
            "periods":{},"errors":[]}
        if since >= until:
            raise ValueError("Requested range contains no published history")

        if wanted & {"1d","1w","1M"}:
            daily_end = period_open(until,"1d")
            try:
                fetched = self.sources.fetch_history(instrument,utc_datetime(since),utc_datetime(daily_end-1))
                added,repaired = self._save(instrument,"1d",fetched.data,since,daily_end)
                rows = live_index_rows(instrument,self.store.get_range(instrument.storage_symbol,"1d",since,daily_end-1))
                coverage = {}
                try:
                    _,dates,_ = session_dates(instrument.calendar or instrument.market,utc_datetime(since).date(),utc_datetime(daily_end-1).date())
                    sessions=set(dates)
                    rows=[row for row in rows if utc_datetime(int(row[0])).date().isoformat() in sessions]
                    present={utc_datetime(int(row[0])).date().isoformat() for row in rows}
                    missing=[day for day in dates if day not in present]
                    coverage.update(expected_sessions=len(dates),missing_sessions=len(missing),
                        first_missing=next(iter(missing),None),last_missing=missing[-1] if missing else None)
                except (ValueError,KeyError) as exc:
                    coverage["calendar_error"]=str(exc)
                daily = {**self._inventory(rows,added,repaired),**coverage,"source":fetched.source,
                    "close_only_rows":sum(not full_index_row(row) for row in rows)}
                result["periods"]["1d"]=daily
                for period in ("1w","1M"):
                    if period in wanted:
                        derived=aggregate(rows,period)
                        result["periods"][period]={**self._inventory(derived,0,0),"source":"stored-daily"}
                self.progress({"symbol":symbol,"timeframe":"1d",**daily})
            except Exception as exc:
                result["errors"].append({"timeframe":"1d","error":str(exc)})
                self.progress({"symbol":symbol,**result["errors"][-1]})

        # Fetch the underlying source periods once. 30m and 4h remain exact
        # aggregations of saved 15m/hourly observations, including after expiry.
        for period,outputs in (("1m",{"1m"}),("5m",{"5m"}),("15m",{"15m","30m"}),("1h",{"1h","4h"})):
            if not wanted & outputs:
                continue
            offset = index_symbol(symbol).metadata["candle_offset_ms"].get(period,0)
            boundary_period = "4h" if period=="1h" else "30m" if period=="15m" else period
            lower = period_open(max(since,now-RETENTION[period]*DAY),boundary_period,offset)
            lower = max(lower,live_start_ms(instrument))
            span = (7 if period=="1m" else 365 if period=="1h" else 59)*DAY
            until_confirmed = min(until,now-15*60_000)
            counts = {target:[0,0] for target in outputs}
            while lower < until_confirmed:
                upper = min(lower+span,until_confirmed)
                try:
                    rows = self.client.history(symbol,"60m" if period=="1h" else period,lower,upper-1)
                    for target in outputs:
                        selected = aggregate(rows,target,offset) if target!=period else rows
                        added,repaired = self._save(instrument,target,selected,lower,upper)
                        counts[target][0] += added
                        counts[target][1] += repaired
                    self.progress({"symbol":symbol,"timeframe":period,"start":utc_datetime(lower).isoformat(),
                        "end":utc_datetime(upper).isoformat(),"received":len(rows)})
                except Exception as exc:
                    result["errors"].append({"timeframe":period,"start":lower,"end":upper,"error":str(exc)})
                    self.progress({"symbol":symbol,**result["errors"][-1]})
                lower = upper
            for target in sorted(outputs):
                rows = live_index_rows(instrument,self.store.get_range(instrument.storage_symbol,target,since,until_confirmed-1))
                result["periods"][target] = self._inventory(rows,*counts[target])
        result["status"] = "error" if result["errors"] else "saved"
        return result

    @staticmethod
    def _inventory(rows,added,repaired):
        return {"rows":len(rows),"added":added,"repaired":repaired,
            "first":utc_datetime(int(rows[0][0])).isoformat() if rows else None,
            "last":utc_datetime(int(rows[-1][0])).isoformat() if rows else None}
