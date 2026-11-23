"""Read the former intraday snapshot cache without altering its immutable records."""
from datetime import datetime, timezone

from sqlalchemy import text

from app.domain.market.candles import candle_end_ms


class LegacyCryptoHistoryReader:
    def __init__(self, engine):
        self.engine = engine

    def read(self, symbol, timeframe, start_ms, end_ms, *, now_ms):
        source = "perpetual" if symbol.upper().endswith(":PERPETUAL") else "spot"
        query = text("""
            SELECT b.observed_at, b.open, b.high, b.low, b.close, b.volume
            FROM signal_lab_price_bars b JOIN signal_lab_price_snapshots s
              ON b.snapshot_hash = s.snapshot_hash
            WHERE s.canonical_code = :code AND s.timeframe = :timeframe
              AND s.provider = :provider AND s.is_latest = 1
              AND b.observed_at >= :start AND b.observed_at < :end
            ORDER BY s.retrieved_at, s.snapshot_hash, b.observed_at
        """)
        with self.engine.connect() as connection:
            records = connection.execute(query, {
                "code": symbol.upper() + "@BINANCE", "timeframe": timeframe, "provider": source,
                "start": datetime.fromtimestamp(start_ms / 1000, timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat(),
            }).mappings().all()
        rows = {}
        for record in records:
            timestamp = int(datetime.fromisoformat(record["observed_at"]).timestamp() * 1000)
            if candle_end_ms(timestamp, timeframe) <= min(end_ms, now_ms):
                rows[timestamp] = [timestamp, *[float(record[name]) for name in ("open", "high", "low", "close")],
                                   float(record["volume"] or 0)]
        return [rows[key] for key in sorted(rows)]
