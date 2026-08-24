
import unittest
from datetime import datetime
from unittest.mock import MagicMock

import pytz
from utils.time import to_utc
from app.services.market.history_range_coordinator import OhlcvRangeResult
from app.services.tools.dca_service import DCAService

class TestTimezoneLogic(unittest.TestCase):
    def test_time_conversion_basics(self):
        # Test UTC Conversion
        # 2024-01-01 00:00 Beijing -> 2023-12-31 16:00 UTC
        local_time_str = "2024-01-01 00:00:00"
        utc_dt = to_utc(local_time_str, "Asia/Shanghai")
        
        expected_utc = datetime(2023, 12, 31, 16, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(utc_dt, expected_utc)

    def test_dca_calculator_timezone(self):
        calc = DCAService(
            market_data_service=MagicMock(),
            sentiment_service=MagicMock(),
            index_data_service=MagicMock(),
        )
        # Scenario: User wants to buy at 08:00 Beijing Time.
        # 08:00 Beijing = 00:00 UTC.
        # We provide data at 00:00 UTC. It should match.
        
        timezone = "Asia/Shanghai"
        target_time = "08:00" 
        
        # Make a mock dataframe with UTC times
        # 00:00 UTC (Match), 01:00 UTC (No Match)
        
        # Mock data return (list of lists)
        ts_match = int(datetime(2024, 1, 1, 0, 0, tzinfo=pytz.UTC).timestamp() * 1000)
        ts_nomatch = int(datetime(2024, 1, 1, 1, 0, tzinfo=pytz.UTC).timestamp() * 1000)
        
        mock_klines = [
            [ts_match, 100, 100, 100, 100, 1000],
            [ts_nomatch, 101, 101, 101, 101, 1000]
        ]
        
        calc.market_data_service.load_ohlcv_range.return_value = OhlcvRangeResult(mock_klines, [])
        
        # We need to ensure get_kline_data is also mocked for current price check
        calc.market_data_service.get_recent_candles.return_value = [[ts_match, 100, 100, 100, 100, 1000]]
        
        res = calc.calculate_dca(
            symbol="BTC/USDT",
            start_date_str="2024-01-01",
            end_date_str="2024-01-01",
            daily_investment=100,
            target_time_str=target_time,
            timezone=timezone,
            strategy="standard"
        )
        
        if 'error' in res:
            self.fail(f"DCA Failed: {res['error']}")
            
        # Check history. Should have 1 entry (Match)
        self.assertEqual(len(res['history']), 1)
        self.assertEqual(res['history'][0]['price'], 100)
        
        # Scenario 2: User wants to buy at 09:00 Beijing.
        # 09:00 Beijing = 01:00 UTC.
        # Should match the second candle.
        
        res2 = calc.calculate_dca(
            symbol="BTC/USDT",
            start_date_str="2024-01-01",
            end_date_str="2024-01-01",
            daily_investment=100,
            target_time_str="09:00",
            timezone=timezone
        )
        self.assertEqual(len(res2['history']), 1)
        self.assertEqual(res2['history'][0]['price'], 101)
