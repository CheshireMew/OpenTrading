"""Free native daily index feed; no exchange SDK or synthetic pricing proxy."""
from datetime import timedelta

from app.domain.market.index_fetch import IndexFetchResult
from app.domain.market.index_history_policy import live_index_rows
from app.infra.market_data.index_chart import IndexChartClient


class NativeIndexHistoryProvider:
    def fetch_history(self,instrument,source,start_dt,end_dt):
        # Several Asian tickers expose today's daily bar only. Their native
        # intraday feed is separate; Tencent/Sina own Asian daily archives.
        if instrument.market != "US" or not source.yfinance_symbol:
            return IndexFetchResult(data=[],source="yahoo-native")
        client=IndexChartClient()
        try:
            rows=client.history(instrument.symbol,"1d",int(start_dt.timestamp()*1000),
                int((end_dt+timedelta(days=1)).timestamp()*1000)-1)
        finally:
            client.close()
        return IndexFetchResult(data=live_index_rows(instrument,rows),source="yahoo-native")
