"""CLI and chart hydration share confirmed candles, venue identity and synthesis."""
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from app.contracts.chart_workspace import ChartSymbol
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.services.market.crypto_history_sync import CryptoHistorySync
from app.domain.market.history.models import Instrument, PriceBar, PriceSnapshot
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.price_repository import PriceRepository
from scripts.market_data_cli import app as market_data_cli


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
START_MS = int(START.timestamp() * 1000)
ROWS = [[START_MS + index * 900_000, 100, 103, 98, 101, 10] for index in range(4)]


class Gateway:
    max_task_seconds = 90

    def __init__(self, exchange_id="binance", rows=ROWS):
        self.exchange_id = exchange_id
        self.rows = rows
        self.calls = []

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None, **_):
        self.calls.append((symbol, timeframe))
        return [row for row in self.rows if row[0] >= since][:limit], 1

    def sleep_for_rate_limit(self):
        pass


def test_crypto_sync_reuses_shared_history_and_derives_hourly_without_a_second_copy(installed_database_runtime):
    gateway = Gateway()
    service = CryptoHistorySync(installed_database_runtime, gateway=gateway)
    first = service.sync("BTC/USDT", START, START + timedelta(hours=1))
    second = service.sync("BTC/USDT", START, START + timedelta(hours=1))
    assert first["status"] == second["status"] == "complete"
    assert first["fetched_rows"] == second["cached_rows"] == 4
    assert second["fetched_rows"] == 0
    assert first["derived_timeframes"]["1h"]["rows"] == 1
    assert len(gateway.calls) == 1
    with installed_database_runtime.engine.connect() as connection:
        assert connection.execute(text("SELECT timeframe, COUNT(*) FROM klines GROUP BY timeframe")).all() == [("15m", 4)]
        assert connection.execute(text("SELECT COUNT(*) FROM signal_lab_price_snapshots")).scalar_one() == 0


def test_perpetual_candles_keep_separate_identity_from_spot(installed_database_runtime):
    spot = CryptoHistorySync(installed_database_runtime, gateway=Gateway())
    spot.sync("BTC/USDT", START, START + timedelta(hours=1))
    rows = [[row[0], 200, 203, 198, 201, 10] for row in ROWS]
    gateway = Gateway("binanceusdm", rows)
    perpetual = CryptoHistorySync(installed_database_runtime, gateway=gateway)
    result = perpetual.sync("BTC/USDT:PERPETUAL", START, START + timedelta(hours=1))
    assert result["storage_symbol"] == "binance:usdm:BTCUSDT"
    assert gateway.calls == [("BTC/USDT:USDT", "15m")]
    assert spot.store.get_range("BTC/USDT", "15m", START_MS, START_MS)[0][4] == 101
    assert spot.store.get_range("binance:usdm:BTCUSDT", "15m", START_MS, START_MS)[0][4] == 201


def test_crypto_sync_limits_off_grid_requests_to_complete_candles(installed_database_runtime):
    service = CryptoHistorySync(installed_database_runtime, gateway=Gateway())
    result = service.sync("BTC/USDT", START - timedelta(seconds=10), START + timedelta(hours=1, minutes=1))
    assert result["status"] == "complete"
    assert result["rows"] == 4
    with pytest.raises(ValueError, match="no complete"):
        service.sync("BTC/USDT", START + timedelta(seconds=1), START + timedelta(minutes=5))


def test_crypto_sync_surfaces_failed_persistence(installed_database_runtime, monkeypatch):
    service = CryptoHistorySync(installed_database_runtime, gateway=Gateway())

    def unavailable(*_):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(service.store, "save", unavailable)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        service.sync("BTC/USDT", START, START + timedelta(hours=1))


def test_crypto_cli_reports_partial_history_as_json_with_a_nonzero_exit(installed_database_runtime, tmp_path, monkeypatch):
    import json
    import config
    from config.settings import AppSettings
    from scripts.market_data import data_commands

    settings = AppSettings(_env_file=None, DATABASE_URL=installed_database_runtime.database_url,
                           RUNTIME_ROOT_DIR=tmp_path / "runtime")
    monkeypatch.setattr(config, "settings", settings)
    gateway = Gateway(rows=ROWS[:2])
    monkeypatch.setattr(data_commands, "CryptoHistorySync",
                        lambda database: CryptoHistorySync(database, gateway=gateway))
    result = CliRunner().invoke(market_data_cli, ["data", "crypto-sync", "--symbol", "BTC/USDT",
        "--start", START.isoformat(), "--end", (START + timedelta(hours=1)).isoformat()])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["schema_version"] == "opentrading.crypto-sync.v1"
    assert payload["status"] == "partial"
    assert payload["results"][0]["missing_ranges"]


def test_former_snapshot_history_fills_only_missing_shared_candles(installed_database_runtime, tmp_path, monkeypatch):
    root = tmp_path / "legacy"
    snapshot = PriceSnapshot(
        instrument=Instrument("BTC/USDT@BINANCE", "BTC/USDT", "crypto", "crypto", "binance", "USDT", "UTC"),
        timeframe="15m", provider="spot", requested_start=START.date(), requested_end=START.date(),
        retrieved_at=START + timedelta(hours=1), source_snapshot_hash="a" * 64, price_basis="raw",
        metadata={"internal_timeframe": True},
        bars=tuple(PriceBar(START + timedelta(minutes=15 * index), 100, 103, 98, 101, 101, 10) for index in range(4)),
    )
    PriceRepository(MarketHistoryDatabase(root, engine=installed_database_runtime.engine)).save_price_snapshot(snapshot)
    gateway = Gateway()
    service = CryptoHistorySync(installed_database_runtime, gateway=gateway)
    corrected = [START_MS, 100, 104, 98, 102, 10]
    read = service.legacy.read

    def arriving_correction(symbol, timeframe, *args, **kwargs):
        if timeframe == "15m":
            service.store.save("BTC/USDT", "15m", [corrected])
        return read(symbol, timeframe, *args, **kwargs)

    monkeypatch.setattr(service.legacy, "read", arriving_correction)
    result = service.sync("BTC/USDT", START, START + timedelta(hours=1))
    assert result["legacy_rows"] == 3
    assert result["status"] == "complete"
    assert gateway.calls == []
    assert service.store.get_range("BTC/USDT", "15m", START_MS, START_MS)[0] == corrected
    with installed_database_runtime.engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM signal_lab_price_snapshots")).scalar_one() == 1


@pytest.mark.asyncio
async def test_chart_and_cli_reuse_each_others_history(installed_database_runtime, monkeypatch):
    gateway = Gateway()
    service = CryptoHistorySync(installed_database_runtime, gateway=gateway)
    market = ChartWorkspaceMarket(None, None, kline_store=service.store)
    symbol = ChartSymbol(id="binance:spot:BTCUSDT", symbol="BTCUSDT", name="BTC/USDT",
                         exchange="binance", market="spot", currency="USDT", timeframes=["15m", "1h"])
    fetched = []

    async def resolve(_):
        return symbol

    async def rows(_symbol, timeframe, _limit, start, end):
        fetched.append(timeframe)
        return [row for row in ROWS if start <= row[0] <= end]

    monkeypatch.setattr(market, "resolve", resolve)
    monkeypatch.setattr(market, "_fetch_crypto_rows", rows)
    try:
        bars = await market.bars(symbol.id, "15m", 4, START_MS, START_MS + 3_600_000 - 1)
        assert len(bars.bars) == 4
        cached = service.sync("BTC/USDT", START, START + timedelta(hours=1))
        assert cached["fetched_rows"] == 0
        assert gateway.calls == []
        hourly = await market.bars(symbol.id, "1h", 1, START_MS, START_MS + 3_600_000 - 1)
        assert len(hourly.bars) == 1
        assert hourly.bars[0].volume == 40
        assert fetched == ["15m"]
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_chart_live_candle_is_visible_without_entering_confirmed_history(installed_database_runtime, monkeypatch):
    import app.services.chart_workspace_market as chart_module

    now = START_MS + 3_600_000 + 450_000
    monkeypatch.setattr(chart_module.time, "time", lambda: now / 1000)
    service = CryptoHistorySync(installed_database_runtime, gateway=Gateway())
    market = ChartWorkspaceMarket(None, None, kline_store=service.store)
    symbol = ChartSymbol(id="binance:spot:BTCUSDT", symbol="BTCUSDT", name="BTC/USDT",
                         exchange="binance", market="spot", currency="USDT", timeframes=["15m"])
    rows = [ROWS[-1], [START_MS + 3_600_000, 101, 104, 100, 103, 3]]

    async def resolve(_):
        return symbol

    async def fetch(_info, _timeframe, _limit, start, end):
        return [row for row in rows if start <= row[0] <= end]

    monkeypatch.setattr(market, "resolve", resolve)
    monkeypatch.setattr(market, "_fetch_crypto_rows", fetch)
    try:
        result = await market.bars(symbol.id, "15m", 2, rows[0][0], now)
        assert [bar.closed for bar in result.bars] == [True, False]
        cached = service.store.get_range("BTC/USDT", "15m", START_MS, now)
        assert cached == [ROWS[-1]]
    finally:
        await market.close()
