"""REST and websocket connections used by chart-market adapters."""
import httpx
import websockets
from app.domain.market.candles import candle_end_ms
from app.infra.market_data.exchange import MarketDataError, normalize_ohlcv, okx_interval

MarketHttpError = httpx.HTTPError


class ChartMarketClient:
    def __init__(self, transport=None):
        self._client = httpx.AsyncClient(timeout=25, transport=transport)

    async def _get_json(self, path, **params):
        response = await self._client.get("https://www.okx.com/api/v5/" + path, params=params)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataError("OKX 行情返回内容无效，请稍后重试") from exc
        if not isinstance(payload, dict) or payload.get("code") != "0" or not isinstance(payload.get("data"), list):
            raise MarketDataError("OKX 行情暂不可用，请稍后重试")
        return payload["data"]

    async def okx_symbol(self, symbol):
        return (await self._get_json("public/instruments", instType="SPOT", instId=symbol))[0]

    async def okx_ticker(self, symbol):
        return (await self._get_json("market/ticker", instId=symbol))[0]

    async def okx_history(self, symbol, timeframe, limit, start, end):
        interval = okx_interval(timeframe)
        upper = end
        if start is not None:
            boundary = start
            for _ in range(limit):
                boundary = candle_end_ms(boundary, timeframe)
            upper = min(upper, boundary - 1)
        rows = {}
        while len(rows) < limit:
            payload = await self._get_json("market/history-candles", instId=symbol, bar=interval,
                                           after=upper + 1, limit=min(limit - len(rows), 100))
            batch = normalize_ohlcv(payload)
            if not batch:
                break
            rows.update({row[0]: row for row in batch if row[0] <= end and (start is None or row[0] >= start)})
            following = min(item[0] for item in batch) - 1
            if following >= upper or (start is not None and following < start):
                break
            upper = following
        return [rows[key] for key in sorted(rows, reverse=True)][:limit]

    def websocket(self, url):
        return websockets.connect(url, open_timeout=15, ping_interval=20)

    async def aclose(self):
        await self._client.aclose()
