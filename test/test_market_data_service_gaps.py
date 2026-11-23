from __future__ import annotations

from datetime import datetime, timedelta

from app.services.market.market_data_service import MarketDataService
import app.services.market.market_data_service as market_data_module
from config import settings
from datetime import timezone
from app.infra.persistence.market.kline_store import KlineStore
from app.infra.db.schema import Kline
from app.domain.market.candles import candle_end_ms


class FakeKlineStore:
    def __init__(self, cached_rows: list[list[float]]) -> None:
        self.cached_rows = list(cached_rows)
        self.saved_rows: list[list[float]] = []

    def get_range(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list[list[float]]:
        return [row for row in self.cached_rows if start_ts <= row[0] <= end_ts]

    def save(self, symbol: str, timeframe: str, klines: list[list[float]]) -> None:
        self.saved_rows.extend(klines)
        self.cached_rows.extend(klines)


class FakeExchangeGateway:
    exchange_id = "binance"
    max_task_seconds = 60

    def __init__(self, rows_by_since: dict[int, list[list[float]] | list[float]]) -> None:
        self.rows_by_since = rows_by_since
        self.calls: list[tuple[str, str, int | None, int | None, int | None]] = []

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
        max_retries: int | None = None,
    ):
        self.calls.append((symbol, timeframe, since, limit, max_retries))
        rows = self.rows_by_since.get(int(since or 0))
        if not rows:
            return [], 1
        if rows and isinstance(rows[0], list):
            return rows, 1
        return [rows], 1

    def sleep_for_rate_limit(self) -> None:
        return


def test_load_ohlcv_range_repairs_middle_gap():
    base = datetime(2024, 1, 1, 0, 0, 0)
    one_hour_ms = 60 * 60 * 1000
    base_ts = int(base.timestamp() * 1000)

    first_row = [base_ts, 1.0, 1.0, 1.0, 1.0, 10.0]
    missing_row = [base_ts + one_hour_ms, 2.0, 2.0, 2.0, 2.0, 20.0]
    third_row = [base_ts + (2 * one_hour_ms), 3.0, 3.0, 3.0, 3.0, 30.0]

    exchange_gateway = FakeExchangeGateway({missing_row[0]: missing_row})
    kline_store = FakeKlineStore([first_row, third_row])
    service = MarketDataService(
        exchange_gateway=exchange_gateway,
        kline_store=kline_store,
    )

    result = service.load_ohlcv_range(
        "BTC/USDT",
        "1h",
        base,
        base + timedelta(hours=2),
    )

    data = result.rows
    assert result.complete
    assert [row[0] for row in data] == [first_row[0], missing_row[0], third_row[0]]
    assert exchange_gateway.calls == [("BTC/USDT", "1h", missing_row[0], settings.EXCHANGE_FETCH_LIMIT, None)]
    assert kline_store.saved_rows == [missing_row]


def test_recent_candles_uses_bounded_live_refresh_instead_of_gap_hydration(monkeypatch):
    base = datetime(2024, 1, 1, 0, 0, 0)
    one_hour_ms = 60 * 60 * 1000
    base_ts = int(base.timestamp() * 1000)

    first_row = [base_ts, 1.0, 1.0, 1.0, 1.0, 10.0]
    missing_row = [base_ts + one_hour_ms, 2.0, 2.0, 2.0, 2.0, 20.0]
    third_row = [base_ts + (2 * one_hour_ms), 3.0, 3.0, 3.0, 3.0, 30.0]
    now_ts = base_ts + (3 * one_hour_ms)
    monkeypatch.setattr(market_data_module.time, "time", lambda: now_ts / 1000)

    exchange_gateway = FakeExchangeGateway({0: [missing_row]})
    kline_store = FakeKlineStore([first_row, third_row])
    service = MarketDataService(
        exchange_gateway=exchange_gateway,
        kline_store=kline_store,
    )

    rows = service.get_recent_candles("BTC/USDT", "1h", 3, allow_cached_response=True)

    assert [row[0] for row in rows] == [first_row[0], missing_row[0], third_row[0]]
    assert exchange_gateway.calls == [("BTC/USDT", "1h", None, 3, settings.EXCHANGE_TAIL_MAX_RETRIES)]
    assert kline_store.saved_rows == [missing_row]


def test_open_and_legacy_cached_bars_are_revalidated_after_close(installed_database_runtime, monkeypatch):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    stamp = int(base.timestamp() * 1000)
    now = [stamp + 1_800_000]
    monkeypatch.setattr(market_data_module.time, "time", lambda: now[0] / 1000)
    store = KlineStore(database_runtime=installed_database_runtime)
    partial = [stamp, 100, 101, 99, 100, 10]
    gateway = FakeExchangeGateway({0: [partial]})
    service = MarketDataService(exchange_gateway=gateway, kline_store=store)
    assert service.get_recent_candles("BTC/USDT", "1h", 1) == [partial]
    assert store.get_range("BTC/USDT", "1h", stamp, stamp) == []
    # A migrated row has no proof that it was observed after close.
    with installed_database_runtime.session_scope() as session:
        session.add(Kline(symbol="BTC/USDT", timeframe="1h", timestamp=stamp, open=100, high=101, low=99, close=100, volume=10))
    now[0] = stamp + 7_200_000
    assert store.get_range("BTC/USDT", "1h", stamp, stamp) == []
    final = [stamp, 100, 115, 97, 110, 100]
    gateway.rows_by_since[stamp] = [final]
    result = service.load_ohlcv_range("BTC/USDT", "1h", base, base + timedelta(hours=1) - timedelta(milliseconds=1))
    assert result.complete and result.rows == [final]
    assert store.get_range("BTC/USDT", "1h", stamp, stamp) == [final]
    # A late partial observation must not replace an already confirmed close.
    now[0] = stamp + 1_800_000
    store.save("BTC/USDT", "1h", [partial])
    assert store.get_range("BTC/USDT", "1h", stamp, stamp) == [final]


def test_monthly_finality_uses_calendar_months():
    stamp = int(datetime(2024, 2, 1, tzinfo=timezone.utc).timestamp() * 1000)
    assert candle_end_ms(stamp, "1M") == int(datetime(2024, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
