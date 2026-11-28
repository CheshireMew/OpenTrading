from __future__ import annotations

from app.application.errors import InvalidRequestError

from datetime import datetime, timezone, timedelta
from app.infra.market_calendar import session_dates
from app.domain.market.session_history import SessionHistoryCoverage
from app.domain.market.index_history_policy import full_index_row, valid_index_row, live_index_rows, live_start_ms, utc_datetime

from app.domain.market.index_catalog import (
    IndexInstrument,
    get_index_instrument,
    get_supported_index_symbols,
)
from app.infra.executor import run_external_io
from app.services.market.history_range_coordinator import HistoryRangeCoordinator
from app.services.market.index_currency_conversion import convert_ohlcv_rows_to_usd
from app.domain.market.index_history import MarketIndexHistoryRecord, OhlcvRecord
from app.services.market.index_history_sources import IndexFetchResult, IndexHistorySources
from app.application.persistence_ports import KlineStorePort


class IndexDataService:
    def __init__(
        self,
        kline_store: KlineStorePort,
        history_sources: IndexHistorySources | None = None,
    ) -> None:
        self.kline_store = kline_store
        self.history_ranges = HistoryRangeCoordinator(kline_store)
        self.history_sources = history_sources or IndexHistorySources()
        self.supported_timeframes = {"1d"}

    def get_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str | None = None,
    ) -> MarketIndexHistoryRecord:
        instrument = self._validate(symbol, timeframe)
        return self._get_series_history(
            instrument=instrument,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            storage_symbol=instrument.storage_symbol,
            fetcher=self.history_sources.fetch_history,
            price_basis="index",
            pricing_symbol=instrument.pricing_symbol,
            pricing_name=instrument.pricing_name,
            pricing_currency=instrument.pricing_currency or instrument.currency,
            native_currency=instrument.currency,
        )

    async def get_history_async(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str | None = None,
    ) -> MarketIndexHistoryRecord:
        return await run_external_io(
            lambda: self.get_history(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
            )
        )

    def get_pricing_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str | None = None,
    ) -> MarketIndexHistoryRecord:
        instrument = self._validate(symbol, timeframe)
        if (
            not instrument.pricing_symbol
            or not instrument.pricing_storage_symbol
            or not self.history_sources.has_pricing_source(instrument)
        ):
            raise InvalidRequestError(f"{instrument.symbol} 暂无默认 ETF 代理价格")
        return self._get_series_history(
            instrument=instrument,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            storage_symbol=instrument.pricing_storage_symbol,
            fetcher=self.history_sources.fetch_pricing_history,
            price_basis="proxy_etf",
            pricing_symbol=instrument.pricing_symbol,
            pricing_name=instrument.pricing_name,
            pricing_currency="USD",
            native_currency=instrument.pricing_currency or instrument.currency,
        )

    async def get_pricing_history_async(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str | None = None,
    ) -> MarketIndexHistoryRecord:
        return await run_external_io(
            lambda: self.get_pricing_history(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
            )
        )

    def _get_series_history(
        self,
        *,
        instrument: IndexInstrument,
        timeframe: str,
        start_date: str,
        end_date: str | None,
        storage_symbol: str,
        fetcher,
        price_basis: str,
        pricing_symbol: str | None,
        pricing_name: str | None,
        pricing_currency: str,
        native_currency: str,
    ) -> MarketIndexHistoryRecord:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end_date else datetime.now(timezone.utc)
        except ValueError as exc:
            raise InvalidRequestError("日期必须是 YYYY-MM-DD") from exc
        if start_dt > end_dt:
            raise InvalidRequestError("start_date 不能晚于 end_date")

        if price_basis == "index":
            start_dt = max(start_dt, utc_datetime(live_start_ms(instrument)))

        start_ts = int(start_dt.timestamp() * 1000)
        # Daily research covers completed UTC dates only. Never count today's
        # still-changing provider row as a historical observation.
        closed_end = min(end_dt.date(), datetime.now(timezone.utc).date() - timedelta(days=1))
        end_ts_exclusive = int(datetime.combine(closed_end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
        calendar, expected, holidays, calendar_error = None, [], [], None
        try:
            calendar, expected, holidays = session_dates(instrument.calendar or instrument.market, start_dt.date(), closed_end)
        except (ValueError, KeyError) as exc:
            calendar_error = str(exc)
        expected_timestamps = {int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000) for day in expected}
        def missing_sessions(rows):
            found = {int(row[0]) for row in rows if float(row[4]) > 0 and
                (price_basis != "index" or valid_index_row(row))}
            return [(stamp, stamp + 86_400_000) for stamp in sorted(expected_timestamps - found)]
        source = "none"
        cached_rows = self.kline_store.get_range(storage_symbol,timeframe,start_ts,
            max(start_ts,end_ts_exclusive-1))
        existing = {row[0]:row for row in cached_rows}

        def fetch_gap(gap_start: int, gap_end: int) -> list[list[float]]:
            nonlocal source
            window_start = utc_datetime(gap_start)
            window_end = utc_datetime(max(gap_start, gap_end - 1))
            fetch_result = fetcher(instrument, window_start, window_end)
            if not fetch_result.data:
                return []

            if price_basis == "proxy_etf":
                fetch_result = IndexFetchResult(
                    data=convert_ohlcv_rows_to_usd(
                        fetch_result.data,
                        native_currency,
                        window_start,
                        window_end,
                        self.history_sources.fetch_usd_fx_rates,
                    ),
                    source=f"{fetch_result.source}:usd",
                    is_close_only=fetch_result.is_close_only,
                )
                if not fetch_result.data:
                    return []

            source = fetch_result.source
            if price_basis != "index":
                return fetch_result.data
            return [row for row in live_index_rows(instrument,fetch_result.data)
                if row[0] not in existing or not full_index_row(existing[row[0]]) or full_index_row(row)]

        range_result = self.history_ranges.load(
            storage_symbol=storage_symbol,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
            fetch_gap=fetch_gap,
            cached_rows=cached_rows,
            coalesce_gaps=True,
            missing_ranges=missing_sessions if calendar_error is None else None,
        )
        data = [row for row in range_result.rows if (calendar_error is not None or int(row[0]) in expected_timestamps) and float(row[4]) > 0]
        if price_basis == "index":
            data = live_index_rows(instrument,data)
        missing = [utc_datetime(stamp).date().isoformat() for stamp, _ in missing_sessions(data)]
        if source == "none" and range_result.cached_rows:
            source = "cache"
        return MarketIndexHistoryRecord(
            symbol=instrument.symbol,
            name=instrument.name,
            market=instrument.market,
            currency=pricing_currency if price_basis == "proxy_etf" else instrument.currency,
            native_currency=native_currency,
            timeframe=timeframe,
            source=source,
            price_basis=price_basis,
            pricing_symbol=pricing_symbol,
            pricing_name=pricing_name,
            pricing_currency=pricing_currency,
            is_close_only=bool(data) and self._rows_are_close_only(data),
            data=[self._ohlcv_record(row) for row in data],
            coverage=SessionHistoryCoverage(complete=calendar_error is None and not missing, calendar=calendar,
                start_date=start_dt.date().isoformat(), end_date=closed_end.isoformat(), expected_sessions=expected,
                missing_sessions=missing, non_trading_dates=holidays, error=calendar_error),
        )

    def _rows_are_close_only(self, rows: list[list[float]]) -> bool:
        if not rows:
            return False
        for row in rows:
            if len(row) < 6:
                return False
            if not (row[1] == row[2] == row[3] == row[4] and row[5] == 0):
                return False
        return True

    def _ohlcv_record(self, row: list[float]) -> OhlcvRecord:
        return OhlcvRecord(
            timestamp=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )

    def _validate(self, symbol: str, timeframe: str) -> IndexInstrument:
        instrument = get_index_instrument(symbol)
        if not instrument:
            raise InvalidRequestError(f"无效指数。可选: {get_supported_index_symbols()}")
        if timeframe not in self.supported_timeframes:
            raise InvalidRequestError("指数行情第一版只支持 1d 日线")
        return instrument
