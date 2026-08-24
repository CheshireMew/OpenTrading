from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.domain.market.index_catalog import IndexInstrument
from app.services.market.index_history_contracts import IndexFetchResult
from app.services.market.index_history_fred import FredIndexHistoryProvider
from app.services.market.index_history_http import (
    BaostockIndexHistoryProvider,
    CboeIndexHistoryProvider,
    EastmoneyIndexHistoryProvider,
    SohuIndexHistoryProvider,
    YFinanceIndexHistoryProvider,
)
from app.services.market.index_history_parsing import redact_exception_message
from app.services.market.index_history_sina import SinaIndexHistoryProvider
from app.services.market.index_source_catalog import (
    IndexSourceBinding,
    get_index_source_binding,
)
from app.services.fred_api_config_service import read_fred_api_key
from utils.logger import logger


HistoryProvider = Callable[
    [IndexInstrument, IndexSourceBinding, datetime, datetime],
    IndexFetchResult,
]


class IndexHistorySources:
    def __init__(self) -> None:
        self.sina = SinaIndexHistoryProvider()
        self.fred = FredIndexHistoryProvider()
        self.providers: tuple[HistoryProvider, ...] = (
            self.sina.fetch_hk_history,
            self.sina.fetch_cn_history,
            self.sina.fetch_us_history,
            EastmoneyIndexHistoryProvider().fetch_history,
            SohuIndexHistoryProvider().fetch_history,
            BaostockIndexHistoryProvider().fetch_history,
            CboeIndexHistoryProvider().fetch_history,
            YFinanceIndexHistoryProvider().fetch_history,
            self.fred.fetch_history,
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
        source = get_index_source_binding(instrument.symbol)
        for provider in self.providers:
            try:
                result = provider(instrument, source, start_dt, end_dt)
            except Exception as exc:
                safe_error = redact_exception_message(exc, (read_fred_api_key(),))
                provider_name = getattr(provider, "__name__", provider.__class__.__name__)
                errors.append(f"{provider_name}: {safe_error}")
                logger.warning(f"指数数据源失败 {instrument.symbol} {provider_name}: {safe_error}")
                continue
            if result.data:
                return result

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

    def fetch_fred_history(
        self,
        instrument: IndexInstrument,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        source = get_index_source_binding(instrument.symbol)
        return self.fred.fetch_history(instrument, source, start_dt, end_dt)

    def fetch_usd_fx_rates(
        self,
        currency: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, float]:
        return self.fred.fetch_usd_fx_rates(currency, start_dt, end_dt)
