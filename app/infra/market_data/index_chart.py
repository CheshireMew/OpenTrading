"""Native Yahoo index chart transport with a small shared connection pool."""
from datetime import datetime, timezone
import json
import math
import threading
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.domain.market.candles import current_candle_open_ms
from app.infra.market_data.exchange import MarketDataError
from app.infra.market_data.index_source_catalog import get_index_source_binding
from config import settings


class IndexChartClient:
    def __init__(self, transport=None):
        self._lock = threading.Lock()
        self._client = None
        self._transport = transport

    def history(self, symbol: str, interval: str, start: int, end: int) -> list[list[float]]:
        ticker = get_index_source_binding(symbol).yfinance_symbol
        if not ticker:
            raise MarketDataError(f"{symbol} 尚未配置指数数据源")
        request_interval = "15m" if interval == "30m" else interval
        with self._lock:
            if self._client is None:
                self._client = httpx.Client(timeout=settings.INDEX_HISTORY_REQUEST_TIMEOUT,
                    limits=httpx.Limits(max_connections=3, max_keepalive_connections=2),
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, transport=self._transport)
            client = self._client
        error = None
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                with client.stream("GET", f"https://{host}/v8/finance/chart/{quote(ticker, safe='')}",
                    params={"interval": request_interval, "period1": start // 1000, "period2": end // 1000 + 1,
                            "includePrePost": "true"}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 4 * 1024 * 1024:
                            raise MarketDataError(f"{ticker} 数据响应超出大小限制")
                    payload = json.loads(body)
                return self._rows(payload, symbol, ticker, interval, request_interval, end)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, MarketDataError) as exc:
                error = exc
        raise MarketDataError(f"{ticker} 指数数据源暂不可用，请稍后重试：{error}") from error

    @staticmethod
    def _rows(payload, symbol, ticker, interval, request_interval, end):
        chart = payload.get("chart", {}) if isinstance(payload, dict) else {}
        results = chart.get("result")
        if chart.get("error") or not isinstance(results, list) or len(results) != 1:
            raise MarketDataError(f"{ticker} 指数数据源暂不可用")
        result = results[0]
        metadata = result.get("meta", {})
        if metadata.get("symbol") != ticker or metadata.get("instrumentType") != "INDEX":
            raise MarketDataError(f"数据源返回的品种不是 {ticker.lstrip('^')} 指数")
        granularity = metadata.get("dataGranularity")
        if granularity and granularity not in {request_interval, "1h" if request_interval == "60m" else request_interval}:
            raise MarketDataError(f"{ticker} 数据源返回的 K 线周期不匹配")
        zone = ZoneInfo(metadata.get("exchangeTimezoneName", "America/New_York"))
        stamps = result.get("timestamp") or []
        series = result.get("indicators", {}).get("quote") or [{}]
        prices = series[0]
        if not isinstance(stamps, list) or any(len(prices.get(key, [])) != len(stamps) for key in ("open", "high", "low", "close")):
            raise MarketDataError(f"{ticker} K 线数据格式无效")
        # Equity index hourly observations start on the half hour. Preserve the
        # vendor's actual window instead of relabeling e.g. 09:30 as 09:00.
        offset = 1_800_000 if interval == "60m" and symbol not in {"US_VIX", "US_DXY"} else 0
        rows = {}
        for index, timestamp in enumerate(stamps):
            if timestamp * 1000 > end:
                continue
            raw = [prices[key][index] for key in ("open", "high", "low", "close")]
            if any(value is None for value in raw):
                continue
            session = datetime.fromtimestamp(timestamp, zone)
            stamp = (int(datetime(session.year, session.month, session.day, tzinfo=timezone.utc).timestamp() * 1000)
                if interval == "1d" else current_candle_open_ms(int(timestamp * 1000) - offset,
                    "1h" if interval == "60m" else interval) + offset)
            values = [round(float(value), 2) for value in raw]
            if not all(math.isfinite(value) and value > 0 for value in values) or not (values[2] <= min(values[0], values[3]) <= max(values[0], values[3]) <= values[1]):
                raise MarketDataError(f"{ticker} K 线数值无效")
            # The last live observation may fall inside the preceding bar.
            if stamp in rows:
                bar = rows[stamp]
                bar[2], bar[3], bar[4] = max(bar[2], values[1]), min(bar[3], values[2]), values[3]
            else:
                rows[stamp] = [stamp, *values, 0.0]
        return [rows[stamp] for stamp in sorted(rows)]

    def close(self):
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
