from __future__ import annotations

from datetime import datetime

from app.domain.market.index_catalog import IndexInstrument
from app.services.market.index_history_contracts import IndexFetchResult
from app.services.market.index_history_parsing import IndexHistoryParsing
from app.services.market.index_source_catalog import IndexSourceBinding


class SinaIndexHistoryProvider(IndexHistoryParsing):
    def _fetch_frame(
        self,
        *,
        source_name: str,
        start_dt: datetime,
        end_dt: datetime,
        loader,
    ) -> IndexFetchResult:
        try:
            import akshare as ak
        except ImportError:
            return IndexFetchResult(data=[], source=source_name)
        frame = loader(ak)
        return IndexFetchResult(
            data=self.frame_to_ohlcv(
                frame=frame,
                start_dt=start_dt,
                end_dt=end_dt,
                volume_field="volume",
            ),
            source=source_name,
        )

    def fetch_us_etf_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not instrument.pricing_symbol:
            return IndexFetchResult(data=[], source="sina_us_etf")
        return self._fetch_frame(
            source_name="sina_us_etf",
            start_dt=start_dt,
            end_dt=end_dt,
            loader=lambda ak: ak.stock_us_daily(symbol=instrument.pricing_symbol),
        )

    def fetch_hk_etf_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not instrument.pricing_symbol:
            return IndexFetchResult(data=[], source="sina_hk_etf")
        return self._fetch_frame(
            source_name="sina_hk_etf",
            start_dt=start_dt,
            end_dt=end_dt,
            loader=lambda ak: ak.stock_hk_daily(symbol=instrument.pricing_symbol, adjust=""),
        )

    def fetch_cn_etf_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not instrument.pricing_symbol:
            return IndexFetchResult(data=[], source="sina_cn_etf")
        return self._fetch_frame(
            source_name="sina_cn_etf",
            start_dt=start_dt,
            end_dt=end_dt,
            loader=lambda ak: ak.fund_etf_hist_sina(symbol=instrument.pricing_symbol),
        )

    def fetch_hk_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.sina_hk_symbol:
            return IndexFetchResult(data=[], source="sina_hk")
        return self._fetch_frame(
            source_name="sina_hk",
            start_dt=start_dt,
            end_dt=end_dt,
            loader=lambda ak: ak.stock_hk_index_daily_sina(symbol=source.sina_hk_symbol),
        )

    def fetch_cn_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.sina_cn_symbol:
            return IndexFetchResult(data=[], source="sina_cn")
        return self._fetch_frame(
            source_name="sina_cn",
            start_dt=start_dt,
            end_dt=end_dt,
            loader=lambda ak: ak.stock_zh_index_daily(symbol=source.sina_cn_symbol),
        )

    def fetch_us_history(
        self,
        instrument: IndexInstrument,
        source: IndexSourceBinding,
        start_dt: datetime,
        end_dt: datetime,
    ) -> IndexFetchResult:
        if not source.sina_us_symbol:
            return IndexFetchResult(data=[], source="sina_us")
        return self._fetch_frame(
            source_name="sina_us",
            start_dt=start_dt,
            end_dt=end_dt,
            loader=lambda ak: ak.index_us_stock_sina(symbol=source.sina_us_symbol),
        )
