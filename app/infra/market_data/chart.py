"""REST and websocket connections used by chart-market adapters."""
import httpx
import websockets
from app.domain.market.candles import candle_end_ms

MarketHttpError = httpx.HTTPError


class ChartMarketClient:
    def __init__(self, transport=None):
        self._client = httpx.AsyncClient(timeout=25, transport=transport)

    async def _get_json(self, path, **params):
        response = await self._client.get("https://www.okx.com/api/v5/" + path, params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "0":
            raise ValueError("OKX market data is unavailable")
        return payload["data"]

    async def okx_symbol(self, symbol):
        return (await self._get_json("public/instruments", instType="SPOT", instId=symbol))[0]

    async def okx_ticker(self, symbol):
        return (await self._get_json("market/ticker", instId=symbol))[0]

    async def okx_history(self, symbol, timeframe, limit, start, end):
        interval = {"1h": "1H", "4h": "4H", "1d": "1Dutc", "1w": "1Wutc", "1M": "1Mutc"}.get(timeframe, timeframe)
        upper = end
        if start is not None:
            boundary = start
            for _ in range(limit):
                boundary = candle_end_ms(boundary, timeframe)
            upper = min(upper, boundary - 1)
        rows = []
        while len(rows) < limit:
            payload = await self._get_json("market/history-candles", instId=symbol, bar=interval,
                                           after=upper + 1, limit=min(limit - len(rows), 100))
            batch = [[int(item[0]), *map(float, item[1:6])] for item in payload]
            if not batch:
                break
            rows.extend(batch)
            following = min(item[0] for item in batch) - 1
            if following >= upper or (start is not None and following < start):
                break
            upper = following
        return rows

    def websocket(self, url):
        return websockets.connect(url, open_timeout=15, ping_interval=20)

    async def aclose(self):
        await self._client.aclose()
