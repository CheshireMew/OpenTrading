"""History must survive tiering, failures and corrections without network access."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, func, select, text

from app.domain.market.resampling import aggregate_complete, synthesis_sources
from app.infra.db.schema import Kline, KlineArchiveSegment
from app.infra.persistence.data_retention import archive_batch
from app.infra.persistence.market.kline_archive import KlineArchive, record_bytes
from app.infra.persistence.market.kline_store import KlineStore
from scripts.market_storage import fingerprints, restore, verify

START = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def candles(count=6, interval=300_000):
    return [[START + i * interval, 100.0 + i, 110.0 + i, 90.0 + i, 101.0 + i, 0.25 + i]
            for i in range(count)]


def count_hot(runtime, timeframe=None):
    with runtime.session_scope() as session:
        query = select(func.count()).select_from(Kline)
        if timeframe:
            query = query.where(Kline.timeframe == timeframe)
        return session.scalar(query)


def move(runtime, batch_size=3):
    return archive_batch(runtime, cutoff_ts=START + 86_400_000, batch_size=batch_size)


def test_archive_preserves_exact_values_flags_and_normal_queries(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    rows = candles()
    store.save("ETH/USDT", "5m", rows)
    with runtime.session_scope() as session:
        session.execute(text("UPDATE klines SET finalized=0 WHERE timestamp=:timestamp"), {"timestamp": rows[2][0]})
    baseline = fingerprints(runtime)
    assert move(runtime) == 3
    assert move(runtime) == 3
    assert move(runtime) == 0
    assert count_hot(runtime) == 0
    assert fingerprints(runtime) == baseline
    assert store.get_range("ETH/USDT", "5m", START, START + 2_000_000) == rows[:2] + rows[3:]
    assert store.get_before("ETH/USDT", "5m", START + 2_000_000, 2) == rows[-2:]
    with runtime.session_scope() as session:
        original = store.archive.read(session, "ETH/USDT", "5m", START, START + 2_000_000,
                                      finalized_only=False)
    assert [record_bytes(r) for r in original] == [record_bytes((*r, i != 2)) for i, r in enumerate(rows)]
    assert verify(runtime)["verified_original_rows"] == 6


def test_failed_file_verification_leaves_all_hot_rows(installed_database_runtime, monkeypatch):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    store.save("ETH/USDT", "5m", candles())
    original = KlineArchive.write_verified

    def fail_after_write(self, *args):
        original(self, *args)
        raise RuntimeError("simulated interruption after file write")

    monkeypatch.setattr(KlineArchive, "write_verified", fail_after_write)
    with pytest.raises(RuntimeError, match="interruption"):
        move(runtime)
    assert count_hot(runtime) == 6
    monkeypatch.setattr(KlineArchive, "write_verified", original)
    assert move(runtime) == 3
    assert len(list(runtime.archive_root.rglob("*.parquet"))) == 1


def test_failed_database_commit_retries_without_losing_history(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    store.save("ETH/USDT", "5m", candles())

    def fail_delete(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("DELETE FROM klines"):
            raise RuntimeError("simulated transaction failure")

    event.listen(runtime.engine, "before_cursor_execute", fail_delete)
    try:
        with pytest.raises(RuntimeError, match="transaction failure"):
            move(runtime)
    finally:
        event.remove(runtime.engine, "before_cursor_execute", fail_delete)
    assert count_hot(runtime) == 6
    with runtime.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(KlineArchiveSegment)) == 0
    assert move(runtime) == 3
    assert store.get_range("ETH/USDT", "5m", START, START + 2_000_000) == candles()


def test_corrupt_archive_is_visible_and_never_treated_as_empty(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    store.save("ETH/USDT", "5m", candles())
    move(runtime)
    path = next(runtime.archive_root.rglob("*.parquet"))
    with path.open("r+b") as stream:
        stream.seek(10)
        value = stream.read(1)
        stream.seek(10)
        stream.write(bytes([value[0] ^ 1]))
    with pytest.raises(RuntimeError, match="checksum"):
        store.get_range("ETH/USDT", "5m", START, START + 2_000_000)
    assert count_hot(runtime) == 3


def test_restore_preserves_original_flags_and_newer_hot_corrections(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    rows = candles()
    store.save("ETH/USDT", "5m", rows)
    with runtime.session_scope() as session:
        session.execute(text("UPDATE klines SET finalized=0 WHERE timestamp=:ts"), {"ts": rows[0][0]})
    move(runtime, 6)
    correction = list(rows[1])
    correction[4] = 105.5
    store.save("ETH/USDT", "5m", [correction])
    before_restore = fingerprints(runtime)
    assert restore(runtime)["restored_rows"] == 5
    assert restore(runtime)["restored_rows"] == 0
    assert fingerprints(runtime) == before_restore
    with runtime.session_scope() as session:
        assert session.scalar(select(Kline.finalized).where(Kline.timestamp == START)) is False
    assert store.get_range("ETH/USDT", "5m", START, START + 2_000_000) == [correction, *rows[2:]]


def test_complete_lower_candles_serve_higher_period_without_duplicate_storage(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    rows = candles()
    store.save("ETH/USDT", "5m", rows)
    expected = aggregate_complete(rows, "5m", "15m")
    store.save("ETH/USDT", "15m", expected)
    assert count_hot(runtime, "15m") == 0
    assert store.get_range("ETH/USDT", "15m", START, START + 2_000_000) == expected
    move(runtime, 6)
    assert store.get_before("ETH/USDT", "15m", START + 2_000_000, 2) == expected


def test_missing_or_unconfirmed_lower_bar_never_fabricates_higher_candle(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    rows = candles(3)
    store.save("ETH/USDT", "5m", rows[:2])
    assert store.get_range("ETH/USDT", "15m", START, START) == []
    store.save("ETH/USDT", "5m", rows[2:])
    with runtime.session_scope() as session:
        session.execute(text("UPDATE klines SET finalized=0 WHERE timestamp=:ts"), {"ts": rows[2][0]})
    assert store.get_range("ETH/USDT", "15m", START, START) == []
    original = [START, 1, 2, 0.5, 1.5, 100]
    store.save("ETH/USDT", "15m", [original])
    assert store.get_range("ETH/USDT", "15m", START, START) == [original]


def test_original_coarse_candles_override_differing_aggregates(installed_database_runtime):
    store = KlineStore(database_runtime=installed_database_runtime)
    original = [START, 1, 2, 0.5, 1.5, 100]
    store.save("ETH/USDT", "15m", [original])
    store.save("ETH/USDT", "5m", candles(3))
    assert store.get_range("ETH/USDT", "15m", START, START) == [original]
    # A correction back to an already archived value must override a hot correction.
    move(installed_database_runtime, 10)
    changed = list(original)
    changed[4] = 1.75
    store.save("ETH/USDT", "15m", [changed])
    store.save("ETH/USDT", "15m", [original])
    assert store.get_range("ETH/USDT", "15m", START, START) == [original]


def test_unchanged_writes_do_not_update_rows_but_corrections_do(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    row = candles(1)[0]
    store.save("ETH/USDT", "5m", [row])
    counts = []

    def affected(_conn, cursor, statement, _params, _ctx, _many):
        if statement.startswith("INSERT INTO klines"):
            counts.append(cursor.rowcount)

    event.listen(runtime.engine, "after_cursor_execute", affected)
    try:
        store.save("ETH/USDT", "5m", [row])
        changed = list(row)
        changed[4] = 102
        store.save("ETH/USDT", "5m", [changed])
    finally:
        event.remove(runtime.engine, "after_cursor_execute", affected)
    assert counts == [0, 1]
    move(runtime)
    store.save("ETH/USDT", "5m", [changed])
    assert count_hot(runtime) == 0


def test_thirty_minute_archival_preserves_history_and_daily_stays_hot(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    rows = candles(2, 1_800_000)
    store.save("ETH/USDT", "30m", rows)
    store.save("ETH/USDT", "1d", [rows[0]])
    assert move(runtime) == 2
    assert count_hot(runtime, "1d") == 1
    assert store.get_range("ETH/USDT", "30m", START, START + 2_000_000) == rows


def test_session_markets_are_not_synthesized():
    assert synthesis_sources("index:HK:HSTECH", "1d") == []
    assert synthesis_sources("600519.SH", "1d") == []
    assert synthesis_sources("BTC/USDT", "1M")[0] == "1d"
    assert aggregate_complete(candles(3)[1:], "5m", "15m") == []


def test_crypto_week_and_leap_month_follow_calendar_boundaries(installed_database_runtime):
    store = KlineStore(database_runtime=installed_database_runtime)
    february = int(datetime(2024, 2, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [[february + i * 86_400_000, 100 + i, 110 + i, 90 + i, 101 + i, 1]
            for i in range(29)]
    assert aggregate_complete(rows[:-1], "1d", "1M") == []
    expected = [[february, 100, 138, 90, 129, 29]]
    assert aggregate_complete(rows, "1d", "1M") == expected
    monday = february + 4 * 86_400_000  # February 5, not an epoch-anchored Thursday.
    week = aggregate_complete(rows[4:11], "1d", "1w")
    assert week == [[monday, 104, 120, 94, 111, 7]]
    store.save("ETH/USDT", "1d", rows)
    assert store.get_range("ETH/USDT", "1M", february, february) == expected
    assert store.get_before("ETH/USDT", "1M", february + 90 * 86_400_000, 1) == expected
    store.save("ETH/USDT", "1M", expected)
    assert count_hot(installed_database_runtime, "1M") == 0


def test_get_before_finds_derived_history_even_far_before_requested_end(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    rows = candles()
    store.save("ETH/USDT", "5m", rows)
    move(runtime, 6)
    assert store.get_before("ETH/USDT", "15m", START + 365 * 86_400_000, 2) == aggregate_complete(rows, "5m", "15m")


def test_archive_corrections_and_data_health_count_each_candle_once(installed_database_runtime):
    from app.infra.persistence.data_health_repository import DataHealthRepository

    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    row = candles(1)[0]
    store.save("ETH/USDT", "5m", [row])
    move(runtime)
    changed = list(row)
    changed[4] = 102.75
    store.save("ETH/USDT", "5m", [changed])
    assert DataHealthRepository(runtime).snapshot()["klines"][0]["count"] == 1
    move(runtime)
    assert store.get_range("ETH/USDT", "5m", START, START) == [changed]
    assert DataHealthRepository(runtime).snapshot()["klines"][0]["count"] == 1


def test_latest_archive_read_skips_unneeded_older_files(installed_database_runtime, monkeypatch):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    store.save("ETH/USDT", "5m", candles())
    move(runtime, 3)
    move(runtime, 3)
    calls = []
    original = store.archive.read_segment

    def track(segment, **kwargs):
        calls.append(segment.id)
        return original(segment, **kwargs)

    monkeypatch.setattr(store.archive, "read_segment", track)
    assert store.get_before("ETH/USDT", "5m", START + 2_000_000, 1) == candles()[-1:]
    assert len(calls) == 1


def test_newer_unconfirmed_archive_cannot_expose_an_older_confirmed_value(installed_database_runtime):
    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    row = candles(1)[0]
    store.save("ETH/USDT", "5m", [row])
    move(runtime)
    with runtime.session_scope() as session:
        session.add(Kline(symbol="ETH/USDT", timeframe="5m", timestamp=START, open=row[1], high=row[2],
                          low=row[3], close=row[4], volume=row[5], finalized=False))
    move(runtime)
    assert store.get_range("ETH/USDT", "5m", START, START) == []
    with runtime.session_scope() as session:
        raw = store.archive.read(session, "ETH/USDT", "5m", START, START, finalized_only=False)
    assert raw[0][6] is False
