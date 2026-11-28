from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.domain.market.index_catalog import IndexInstrument
from app.domain.market.index_fetch import IndexFetchResult
from app.domain.market.index_history_policy import full_index_row, live_index_rows, live_start_ms, utc_datetime
from app.infra.market_calendar import session_dates
from app.infra.market_data.index_history_fx import IndexCurrencyHistoryProvider
from app.infra.market_data.index_history_http import (
    BaostockIndexHistoryProvider,
    CboeIndexHistoryProvider,
    EastmoneyIndexHistoryProvider,
    SohuIndexHistoryProvider,
    YFinanceIndexHistoryProvider,
)
from app.infra.market_data.index_history_parsing import redact_exception_message
from app.infra.market_data.index_history_sina import SinaIndexHistoryProvider
from app.infra.market_data.index_history_tencent import TencentIndexHistoryProvider
from app.infra.market_data.index_history_native import NativeIndexHistoryProvider
from app.infra.market_data.index_history_archives import NasdaqIndexHistoryProvider, DowJonesHistoryProvider
from app.infra.market_data.index_source_catalog import (
    IndexSourceBinding,
    get_index_source_binding,
)
from utils.logger import logger


HistoryProvider = Callable[
    [IndexInstrument, IndexSourceBinding, datetime, datetime],
    IndexFetchResult,
]


class IndexHistorySources:
    def __init__(self) -> None:
        self.sina = SinaIndexHistoryProvider()
        self.currency = IndexCurrencyHistoryProvider()
        self.providers: tuple[HistoryProvider, ...] = (
            TencentIndexHistoryProvider().fetch_history,
            NativeIndexHistoryProvider().fetch_history,
            NasdaqIndexHistoryProvider().fetch_history,
            self.sina.fetch_hk_history,
            self.sina.fetch_cn_history,
            self.sina.fetch_us_history,
            EastmoneyIndexHistoryProvider().fetch_history,
            DowJonesHistoryProvider().fetch_history,
            SohuIndexHistoryProvider().fetch_history,
            BaostockIndexHistoryProvider().fetch_history,
            CboeIndexHistoryProvider().fetch_history,
            YFinanceIndexHistoryProvider().fetch_history,
        )
        self.pricing_providers = {
            "sina_us_etf": self.sina.fetch_us_etf_history,
            "sina_hk_etf": self.sina.fetch_hk_etf_history,
            "sina_cn_etf": self.sina.fetch_cn_etf_history,
        }

    def fetch_history(
        self,
        instrument: IndexInstrument,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        errors: list[str] = []
        start_dt = max(start_dt.replace(tzinfo=timezone.utc) if start_dt.tzinfo is None else start_dt, utc_datetime(live_start_ms(instrument)))
        end_dt = end_dt.replace(tzinfo=timezone.utc) if end_dt.tzinfo is None else end_dt
        if end_dt < start_dt:
            return IndexFetchResult(data=[], source="not-launched")
        source = get_index_source_binding(instrument.symbol)
        providers = self.providers
        if instrument.symbol == "US_VIX":
            providers = tuple(sorted(providers, key=lambda provider:
                not isinstance(getattr(provider,"__self__",None), CboeIndexHistoryProvider)))
        merged, sources = {}, []
        calendar_known = True
        try:
            _, days, _ = session_dates(instrument.calendar or instrument.market,start_dt.date(),end_dt.date())
            expected = {int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()*1000) for day in days}
        except (ValueError,KeyError):
            expected = set()
            calendar_known = False
        for provider in providers:
            request_start, request_end = start_dt, end_dt
            if calendar_known and merged:
                missing = sorted(expected - {stamp for stamp,row in merged.items() if full_index_row(row)})
                if missing:
                    request_start = max(start_dt, utc_datetime(missing[0]))
                    request_end = min(end_dt, utc_datetime(missing[-1]).replace(hour=23,minute=59,second=59))
            try:
                result = provider(instrument, source, request_start, request_end)
            except Exception as exc:
                safe_error = redact_exception_message(exc)
                provider_name = getattr(provider, "__name__", provider.__class__.__name__)
                errors.append(f"{provider_name}: {safe_error}")
                logger.warning(f"指数数据源失败 {instrument.symbol} {provider_name}: {safe_error}")
                continue
            rows = [row for row in live_index_rows(instrument,result.data)
                if start_dt.date() <= utc_datetime(int(row[0])).date() <= end_dt.date()
                and (not calendar_known or int(row[0]) in expected)]
            improved = False
            for row in rows:
                previous = merged.get(row[0])
                if previous is None or (not full_index_row(previous) and full_index_row(row)):
                    merged[row[0]] = row
                    improved = True
            if improved:
                sources.append(result.source)
            complete = expected <= {stamp for stamp,row in merged.items() if full_index_row(row)}
            if calendar_known and merged and complete and all(full_index_row(row) for row in merged.values()):
                break
        if merged:
            rows=[merged[stamp] for stamp in sorted(merged)]
            return IndexFetchResult(data=rows,source="+".join(dict.fromkeys(sources)),
                is_close_only=all(not full_index_row(row) for row in rows))

        logger.error(f"指数历史数据获取失败 {instrument.symbol}: {'; '.join(errors)}")
        return IndexFetchResult(data=[], source="none")

    def fetch_pricing_history(
        self,
        instrument: IndexInstrument,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        source = get_index_source_binding(instrument.symbol)
        provider = self.pricing_providers.get(source.pricing_provider or "")
        if provider is None:
            return IndexFetchResult(data=[], source="none")
        return provider(instrument, source, start_dt, end_dt)

    def has_pricing_source(self, instrument: IndexInstrument) -> bool:
        source = get_index_source_binding(instrument.symbol)
        return bool(source.pricing_provider in self.pricing_providers)

    def fetch_usd_fx_rates(
        self,
        currency: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, float]:
        return self.currency.fetch_usd_fx_rates(currency, start_dt, end_dt)
