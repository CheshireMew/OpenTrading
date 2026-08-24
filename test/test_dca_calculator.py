import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.contracts.dto.market_catalog import MarketIndexHistoryResponse
from app.contracts.market_history import build_ohlcv_points

from app.services.market.history_range_coordinator import OhlcvRangeResult
from app.services.tools.dca_service import DCAService


class TestValueAveraging(unittest.TestCase):
    def setUp(self):
        self.calculator = DCAService(
            market_data_service=MagicMock(),
            sentiment_service=MagicMock(),
            index_data_service=MagicMock(),
        )

    def test_value_averaging_zero_invested(self):
        d1 = datetime(2024, 1, 1, 23, 0, tzinfo=timezone.utc)
        d2 = datetime(2024, 1, 2, 23, 0, tzinfo=timezone.utc)
        d3 = datetime(2024, 1, 3, 23, 0, tzinfo=timezone.utc)

        def make_kline(dt, price):
            ts = int(dt.timestamp() * 1000)
            return [ts, price, price, price, price, 1000]

        mock_data = [
            make_kline(d1, 100.0),
            make_kline(d2, 300.0),
            make_kline(d3, 1000.0),
        ]

        self.calculator.market_data_service.load_ohlcv_range.return_value = OhlcvRangeResult(mock_data, [])
        self.calculator.market_data_service.get_recent_candles.return_value = [[
            int(d3.timestamp() * 1000), 1000.0, 1000.0, 1000.0, 1000.0, 1000
        ]]

        result = self.calculator.calculate_dca(
            symbol='BTC/USDT',
            start_date_str='2024-01-01',
            end_date_str='2024-01-03',
            daily_investment=100.0,
            target_time_str='23:00',
            timezone='UTC',
            strategy='value_averaging',
            strategy_params={'fee_rate': 0},
        )

        if 'error' in result:
            self.fail(f"Calculator returned error: {result['error']}")

        h1 = result['history'][1]
        self.assertEqual(h1['invested'], 0.0)
        self.assertEqual(h1['roi'], 0.0)

        h2 = result['history'][2]
        self.assertTrue(h2['invested'] < 0)
        self.assertEqual(h2['roi'], 0.0)
        self.assertEqual(result['data_quality'], 'exchange')

    def test_btc_early_history_is_labeled_synthetic(self):
        early = datetime(2010, 7, 18, 23, 0, tzinfo=timezone.utc)
        timestamp = int(early.timestamp() * 1000)
        mock_data = [[timestamp, 0.08, 0.08, 0.08, 0.08, 1000]]
        self.calculator.market_data_service.load_ohlcv_range.return_value = OhlcvRangeResult(mock_data, [])
        self.calculator.market_data_service.get_recent_candles.return_value = mock_data

        result = self.calculator.calculate_dca(
            symbol='BTC/USDT',
            start_date_str='2010-07-18',
            end_date_str='2010-07-18',
            daily_investment=100.0,
            target_time_str='23:00',
            timezone='UTC',
            strategy='standard',
            strategy_params={'fee_rate': 0},
        )

        self.assertNotIn('error', result)
        self.assertEqual(result['data_quality'], 'synthetic_and_exchange_proxy')

    def test_index_standard_dca_uses_daily_history(self):
        index_service = MagicMock()
        index_service.get_pricing_history.return_value = MarketIndexHistoryResponse(
            symbol="HK_HSI",
            name="Hang Seng Index",
            market="HK",
            currency="HKD",
            native_currency="HKD",
            timeframe="1d",
            source="test",
            price_basis="proxy_etf",
            pricing_symbol="02800",
            pricing_name="Tracker Fund of Hong Kong",
            pricing_currency="USD",
            is_close_only=False,
            count=3,
            data=build_ohlcv_points([
                [1704067200000, 100.0, 100.0, 100.0, 100.0, 0],
                [1704153600000, 110.0, 110.0, 110.0, 110.0, 0],
                [1704240000000, 120.0, 120.0, 120.0, 120.0, 0],
            ]),
        )
        calculator = DCAService(
            market_data_service=MagicMock(),
            sentiment_service=MagicMock(),
            index_data_service=index_service,
        )

        result = calculator.calculate_dca(
            symbol='HK_HSI',
            start_date_str='2024-01-01',
            end_date_str='2024-01-03',
            daily_investment=100.0,
            target_time_str='23:00',
            timezone='Asia/Shanghai',
            strategy='standard',
            strategy_params={'fee_rate': 0},
        )

        self.assertNotIn('error', result)
        self.assertEqual(result['asset_class'], 'index')
        self.assertEqual(result['total_days'], 3)
        self.assertEqual(result['current_price'], 120.0)
        self.assertEqual(result['price_basis'], 'proxy_etf')
        self.assertEqual(result['pricing_symbol'], '02800')
        self.assertEqual(result['pricing_currency'], 'USD')
        self.assertEqual(result['data_quality'], 'index_proxy')
