
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.infra.db import build_database_runtime
from app.infra.db.schema_runtime import prepare_db
from app.infra.persistence.market.kline_store import KlineStore
from app.services.market.market_data_service import MarketDataService
from app.infra.db.schema import Kline
from config.settings import AppSettings


class DeterministicExchangeGateway:
    exchange_id = "binance"
    max_task_seconds = 10

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None, max_retries=None):
        start = int(since or 0)
        rows = [
            [start + index * 3_600_000, 100.0, 101.0, 99.0, 100.5, 1_000.0]
            for index in range(min(limit or 1000, 24))
        ]
        return rows, 1

    def sleep_for_rate_limit(self):
        return None

class CachingTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "cache.db"
        self.database_runtime = build_database_runtime(
            AppSettings(DATABASE_URL=f"sqlite:///{database_path.as_posix()}")
        )
        prepare_db(self.database_runtime)
        self.provider = MarketDataService(
            exchange_gateway=DeterministicExchangeGateway(),
            kline_store=KlineStore(database_runtime=self.database_runtime),
        )
        self.symbol = 'BTC/USDT'
        self.timeframe = '1h'
        
        # Clean up existing Klines for test symbol
        session = self.database_runtime.get_session()
        session.query(Kline).filter_by(symbol=self.symbol).delete()
        session.commit()
        session.close()

    def test_caching_flow(self):
        end_date = datetime(2025, 1, 2, tzinfo=timezone.utc)
        start_date = end_date - timedelta(hours=10)
        
        # 1. First fetch: Should call exchange
        data1 = self.provider.load_ohlcv_range(self.symbol, self.timeframe, start_date, end_date).rows
        self.assertTrue(len(data1) > 0)
        
        # Verify DB has data
        session = self.database_runtime.get_session()
        count = session.query(Kline).filter_by(symbol=self.symbol).count()
        self.assertTrue(count >= len(data1))
        session.close()

        exact_start = datetime.fromtimestamp(data1[0][0] / 1000, tz=timezone.utc)
        exact_end = datetime.fromtimestamp(data1[-1][0] / 1000, tz=timezone.utc)
        
        with patch.object(
            self.provider.exchange_gateway,
            'fetch_ohlcv',
            wraps=self.provider.exchange_gateway.fetch_ohlcv,
        ) as mock_exchange_fetch:
            data2 = self.provider.load_ohlcv_range(self.symbol, self.timeframe, exact_start, exact_end).rows

            self.assertEqual(len(data1), len(data2))
            self.assertEqual(data1[0][0], data2[0][0])
            self.assertEqual(mock_exchange_fetch.call_count, 0)
                
    def tearDown(self):
        self.database_runtime.dispose()
        self.temp_dir.cleanup()
