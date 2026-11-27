"""CLI history hydration through the same store and range coordinator as the application."""
from datetime import datetime, timedelta, timezone
import time

from app.infra.market_data.exchange import ExchangeGateway
from app.infra.persistence.market.kline_store import KlineStore
from app.infra.persistence.market.legacy_crypto_history import LegacyCryptoHistoryReader
from app.services.market.market_data_service import MarketDataService
from app.domain.market.candles import current_candle_open_ms
from config import settings


class CryptoHistorySync:
    def __init__(self, database, *, gateway=None):
        self.store = KlineStore(database_runtime=database)
        self.legacy = LegacyCryptoHistoryReader(database.engine)
        self.market = MarketDataService(
            exchange_gateway=gateway or ExchangeGateway(settings.EXCHANGE_ID),
            kline_store=self.store,
        )

    def close(self):
        self.market.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def sync(self, symbol, start, end):
        if start >= end:
            raise ValueError("start must be earlier than end")
        first_ms = int(start.timestamp() * 1000)
        first_open = current_candle_open_ms(first_ms, "15m")
        first_ms = first_open if first_ms == first_open else first_open + 900_000
        last_ms = min(current_candle_open_ms(int(end.timestamp() * 1000), "15m"),
                      current_candle_open_ms(int(time.time() * 1000), "15m"))
        if first_ms >= last_ms:
            raise ValueError("requested range contains no complete 15-minute candles")
        start = datetime.fromtimestamp(first_ms / 1000, timezone.utc)
        end = datetime.fromtimestamp(last_ms / 1000, timezone.utc)
        storage_symbol = self.market.symbol_routing.storage_symbol(symbol)
        legacy_rows = 0
        exchange = self.market.symbol_routing.gateway_for_symbol(symbol).exchange_id
        if exchange in {"binance", "binanceusdm"}:
            start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
            for timeframe in ("15m", "1h"):
                existing = {int(row[0]) for row in self.store.get_range(storage_symbol, timeframe, start_ms, end_ms - 1)}
                rows = [row for row in self.legacy.read(symbol, timeframe, start_ms, end_ms, now_ms=int(time.time() * 1000))
                        if int(row[0]) not in existing]
                if rows:
                    legacy_rows += self.store.save_missing(storage_symbol, timeframe, rows)
        result = self.market.load_ohlcv_range(symbol, "15m", start, end - timedelta(milliseconds=1), strict=True)
        hourly = self.store.get_range(storage_symbol, "1h", int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1)
        return {
            "symbol": symbol,
            "storage_symbol": storage_symbol,
            "status": "complete" if result.complete else "partial",
            "timeframe": "15m",
            "rows": len(result.rows),
            "cached_rows": len(result.cached_rows),
            "fetched_rows": len(result.fetched_rows),
            "legacy_rows": legacy_rows,
            "missing_ranges": result.missing_ranges,
            "derived_timeframes": {"1h": {"rows": len(hourly), "storage": "shared_kline_synthesis"}},
        }
