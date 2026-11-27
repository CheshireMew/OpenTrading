from __future__ import annotations

import math
import threading
import time
from typing import Optional, Tuple

import httpx

from app.domain.market.candles import candle_end_ms, current_candle_open_ms
from config import settings
from utils.logger import logger


class MarketDataError(RuntimeError):
    """The upstream response is unusable, rather than an empty history page."""


def normalize_ohlcv(payload: object) -> list[list[float]]:
    """Both public APIs return timestamp, OHLC and base volume first."""
    if not isinstance(payload, list):
        raise MarketDataError("交易所返回的 K 线格式无效")
    rows = {}
    for item in payload:
        if not isinstance(item, (list, tuple)) or len(item) < 6:
            raise MarketDataError("交易所返回的 K 线格式无效")
        try:
            timestamp, *values = map(float, item[:6])
        except (ValueError, TypeError) as exc:
            raise MarketDataError("交易所返回的 K 线数值无效") from exc
        if not all(math.isfinite(value) for value in (timestamp, *values)):
            raise MarketDataError("交易所返回的 K 线数值无效")
        rows[int(timestamp)] = [int(timestamp), *values]
    return [rows[key] for key in sorted(rows)]


def okx_interval(timeframe: str) -> str:
    return {"1h": "1H", "2h": "2H", "4h": "4H", "6h": "6Hutc", "12h": "12Hutc",
            "1d": "1Dutc", "3d": "3Dutc", "1w": "1Wutc", "1M": "1Mutc",
            "3M": "3Mutc"}.get(timeframe, timeframe)


class ExchangeGateway:
    """Small, shared REST connection pool; no exchange-wide market tables."""

    def __init__(self, exchange_id: str = settings.EXCHANGE_ID, *, transport=None) -> None:
        if exchange_id not in {"binance", "binanceusdm", "okx"}:
            raise ValueError(f"Unsupported exchange: {exchange_id}")
        self.exchange_id = exchange_id
        self.max_retries = settings.EXCHANGE_MAX_RETRIES
        self.retry_delay = settings.EXCHANGE_RETRY_DELAY
        self.max_task_seconds = settings.EXCHANGE_TASK_TIMEOUT
        self.fetch_limit = 100 if exchange_id == "okx" else 1000
        self._transport = transport
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()
        self._next_request = 0.0
        self._closed = False
        self._request_interval = 0.12 if exchange_id == "okx" else 0.1

    @property
    def client(self) -> httpx.Client:
        with self._lock:
            if self._closed:
                raise RuntimeError("交易所连接已关闭")
            if self._client is None:
                self._client = httpx.Client(
                    timeout=settings.EXCHANGE_REQUEST_TIMEOUT_MS / 1000,
                    limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
                    headers={"accept": "application/json"}, transport=self._transport,
                )
            return self._client

    def _wait_for_slot(self, deadline: float) -> None:
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_request)
            if scheduled >= deadline:
                raise TimeoutError("交易所请求超过等待时限")
            self._next_request = scheduled + self._request_interval
        if scheduled > now:
            time.sleep(scheduled - now)

    def _request(self, symbol: str, timeframe: str, since: int | None, limit: int):
        pair = symbol.split(":", 1)[0].upper()
        if self.exchange_id == "okx":
            params = {"instId": pair.replace("/", "-"), "bar": okx_interval(timeframe), "limit": min(limit, self.fetch_limit)}
            if since is not None:
                boundary = current_candle_open_ms(since, timeframe)
                if boundary < since:
                    boundary = candle_end_ms(boundary, timeframe)
                for _ in range(limit):
                    boundary = candle_end_ms(boundary, timeframe)
                params.update(after=boundary, before=since - 1)
            return "https://www.okx.com/api/v5/market/history-candles", params
        futures = self.exchange_id == "binanceusdm"
        base = settings.BINANCE_FUTURES_USDM_BASE_URL if futures else settings.BINANCE_PUBLIC_BASE_URL
        params = {"symbol": pair.replace("/", ""), "interval": timeframe, "limit": limit}
        if since is not None:
            params["startTime"] = since
        return base.rstrip("/") + ("/fapi/v1/klines" if futures else "/api/v3/klines"), params

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[int] = None,
        limit: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> Tuple[list[list[float]], int]:
        limit = min(max(int(limit if limit is not None else 500), 1), 1000)
        url, params = self._request(symbol, timeframe, since, limit)
        retry_count = max(max_retries if max_retries is not None else self.max_retries, 1)
        deadline = time.monotonic() + self.max_task_seconds
        rows, attempts = {}, 0
        while len(rows) < limit:
            page, count = self._fetch_page(url, params, retry_count, deadline)
            attempts += count
            rows.update({row[0]: row for row in page if since is None or row[0] >= since})
            if self.exchange_id != "okx" or not page or len(page) < int(params["limit"]):
                break
            following = min(row[0] for row in page)
            if (since is not None and following <= since) or following >= int(params.get("after", following + 1)):
                break
            params["after"] = following
            params["limit"] = min(limit - len(rows), self.fetch_limit)
        ordered = [rows[key] for key in sorted(rows)]
        return (ordered[:limit] if since is not None else ordered[-limit:]), attempts

    def _fetch_page(self, url, params, retry_count, deadline):
        for attempt in range(retry_count):
            attempts = attempt + 1
            try:
                self._wait_for_slot(deadline)
                response = self.client.get(url, params=params,
                    timeout=min(settings.EXCHANGE_REQUEST_TIMEOUT_MS / 1000, max(deadline - time.monotonic(), 0.001)))
                response.raise_for_status()
                payload = response.json()
                if self.exchange_id == "okx":
                    if not isinstance(payload, dict) or payload.get("code") != "0":
                        raise MarketDataError("OKX K 线请求失败")
                    payload = payload.get("data")
                return normalize_ohlcv(payload), attempts
            except (httpx.HTTPError, ValueError, MarketDataError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500)
                delay = float(self.retry_delay) * attempts
                if isinstance(exc, httpx.HTTPStatusError):
                    try:
                        delay = max(delay, float(exc.response.headers.get("Retry-After", "0")))
                    except ValueError:
                        pass
                if not retryable or attempts == retry_count or time.monotonic() + delay >= deadline:
                    logger.warning("获取 K 线失败 exchange=%s symbol=%s attempts=%s error=%s",
                                   self.exchange_id, params.get("symbol", params.get("instId")), attempts, type(exc).__name__)
                    # An upstream failure must never masquerade as the start of history.
                    if isinstance(exc, ValueError):
                        raise MarketDataError("交易所返回内容无效，请稍后重试") from exc
                    raise
                time.sleep(delay)
        raise RuntimeError("交易所请求未完成")

    def sleep_for_rate_limit(self) -> None:
        # Requests reserve a paced slot before sending, including concurrent callers.
        pass

    def close(self) -> None:
        with self._lock:
            self._closed = True
            client, self._client = self._client, None
        if client is not None:
            client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
