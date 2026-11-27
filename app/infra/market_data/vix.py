"""Compatibility entry point for the shared native index chart transport."""
from app.infra.market_data.index_chart import IndexChartClient


class VixIntradayClient(IndexChartClient):
    def history(self, interval, start, end):
        return super().history("US_VIX", interval, start, end)
