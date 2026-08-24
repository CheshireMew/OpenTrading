from __future__ import annotations

import importlib
import threading
import time
from typing import Optional, Tuple

from config import settings
from utils.logger import logger


class ExchangeGateway:
    def __init__(self, exchange_id: str = settings.EXCHANGE_ID) -> None:
        self.exchange_id = exchange_id
        self.max_retries = settings.EXCHANGE_MAX_RETRIES
        self.retry_delay = settings.EXCHANGE_RETRY_DELAY
        self.max_task_seconds = settings.EXCHANGE_TASK_TIMEOUT
        self._local = threading.local()
        self._exchange_config = {
            "enableRateLimit": True,
            "timeout": settings.EXCHANGE_REQUEST_TIMEOUT_MS,
            "options": {
                "defaultType": "spot",
            },
        }

    @property
    def exchange(self):
        if not hasattr(self._local, "exchange"):
            ccxt = importlib.import_module("ccxt")
            if not hasattr(ccxt, self.exchange_id):
                logger.error(f"不支持的交易所 ID: {self.exchange_id}")
                raise ValueError(f"Unsupported exchange: {self.exchange_id}")
            exchange_class = getattr(ccxt, self.exchange_id)
            self._local.exchange = exchange_class(self._exchange_config.copy())
            logger.info(f"已初始化交易所连接: {self.exchange_id}")
        return self._local.exchange

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: Optional[int] = None,
        limit: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> Tuple[list[list[float]], int]:
        attempts = 0
        retry_count = max(max_retries if max_retries is not None else self.max_retries, 1)
        for attempt in range(retry_count):
            attempts = attempt + 1
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
                if ohlcv:
                    return ohlcv, attempts
            except Exception as e:
                logger.warning(f"获取 K 线失败 (尝试 {attempts}): {e}")
                if attempt + 1 < retry_count:
                    time.sleep(self.retry_delay)
        return [], attempts

    def sleep_for_rate_limit(self) -> None:
        time.sleep(self.exchange.rateLimit / 1000)
