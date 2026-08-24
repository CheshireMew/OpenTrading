from __future__ import annotations

import time

from app.services.market.symbol_routing import MarketSymbolRouting
from config import settings
from utils.logger import logger


class ExchangeKlineFetcher:
    def __init__(self, symbol_routing: MarketSymbolRouting) -> None:
        self._symbol_routing = symbol_routing

    def fetch_gap(self, symbol: str, timeframe: str, since: int, until: int) -> list[list[float]]:
        data: list[list[float]] = []
        current_since = since
        task_start = time.time()
        fetch_symbol = self._symbol_routing.fetch_symbol(symbol)
        gateway = self._symbol_routing.gateway_for_symbol(symbol)

        while current_since < until:
            limit = settings.EXCHANGE_FETCH_LIMIT
            batch, _attempts = gateway.fetch_ohlcv(
                fetch_symbol,
                timeframe,
                since=current_since,
                limit=limit,
            )
            if not batch:
                break

            filtered = [row for row in batch if row[0] < until]
            if not filtered:
                break
            data.extend(filtered)

            last_ts = int(filtered[-1][0])
            if last_ts < current_since:
                break
            current_since = last_ts + 1
            gateway.sleep_for_rate_limit()

            if len(batch) < limit:
                break
            if time.time() - task_start > gateway.max_task_seconds:
                logger.warning(
                    f"[fetch_gap] 超时终止 symbol={symbol} tf={timeframe} since={since} until={until}"
                )
                break

        return data
