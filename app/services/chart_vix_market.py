"""VIX convenience interface backed by the shared index implementation."""
import time as time
from app.infra.market_data.vix import VixIntradayClient
from app.services.chart_index_catalog import index_symbol, PERIODS as PERIODS, RETENTION as RETENTION
from app.services.chart_index_market import ChartIndexMarket, aggregate as aggregate, DAY as DAY

VIX_ID = "index:index:US_VIX"


def vix_symbol():
    return index_symbol("US_VIX")


class ChartVixMarket(ChartIndexMarket):
    def __init__(self, index, store=None, client=None):
        super().__init__(index, store, client or VixIntradayClient())

    def _fetch_history(self, symbol, interval, start, end):
        return self.client.history(interval, start, end)

    async def _history(self, symbol, interval, start, end):
        return await self._intraday(interval, start, end)

    async def _intraday(self, interval, start, end):
        return await super()._history("US_VIX", interval, start, end)

    async def bars(self, *args):
        return await super().bars(*args if len(args) == 5 else ("US_VIX", *args))

    async def quote(self):
        return await super().quote("US_VIX")
