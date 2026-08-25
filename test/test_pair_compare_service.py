from datetime import datetime
from unittest.mock import MagicMock

from app.contracts.dto.market_catalog import MarketIndexHistoryResponse
from app.contracts.market_history import build_ohlcv_points
from app.services.tools.pair_compare_service import PairCompareService


def test_compare_index_symbols_uses_index_history():
    index_service = MagicMock()
    index_service.get_instrument.side_effect = lambda symbol: object() if symbol in {"HK_HSI", "US_SP500"} else None
    index_service.get_history.side_effect = lambda **kwargs: MarketIndexHistoryResponse(
        symbol=kwargs["symbol"],
        name=kwargs["symbol"],
        market="test",
        currency="USD",
        native_currency="USD",
        timeframe="1d",
        source="test",
        price_basis="index",
        count=2,
        data=build_ohlcv_points([
            [1704067200000, 100.0, 110.0, 90.0, 105.0, 0],
            [1704153600000, 105.0, 120.0, 100.0, 115.0, 0],
        ])
        if kwargs["symbol"] == "HK_HSI"
        else build_ohlcv_points([
            [1704067200000, 10.0, 11.0, 9.0, 10.5, 0],
            [1704153600000, 10.5, 12.0, 10.0, 11.5, 0],
        ]),
    )

    service = PairCompareService(market_data_service=MagicMock(), index_data_service=index_service)
    result = service.compare_pairs("HK_HSI", "US_SP500", days=7, timeframe="1h")

    assert "error" not in result
    assert result["symbol_a"] == "HK_HSI"
    assert result["symbol_b"] == "US_SP500"
    assert result["timeframe"] == "1d"
    assert result["ratio_symbol"] == "HK_HSI/US_SP500"
    assert len(result["ratio_ohlc"]) == 2
    assert result["statistics"]["aligned_points"] == 2
    assert result["statistics"]["symbol_a_return_pct"] == result["statistics"]["symbol_b_return_pct"]
    assert result["statistics"]["excess_return_pct"] == 0


def test_closed_history_window_excludes_the_open_base_candle():
    start, end = PairCompareService._closed_history_window(
        7,
        "5m",
        now=datetime(2026, 8, 24, 10, 7, 42),
    )

    assert end == datetime(2026, 8, 24, 10, 5)
    assert start == datetime(2026, 8, 17, 10, 5)
    assert int(end.timestamp() * 1000) % (5 * 60 * 1000) == 0


def test_compare_hides_internal_history_errors():
    market_service = MagicMock()
    market_service.load_ohlcv_range.side_effect = RuntimeError(
        "BTC/USDT 5m missing_range end=1787537220000"
    )
    service = PairCompareService(
        market_data_service=market_service,
        index_data_service=MagicMock(),
    )

    result = service.compare_pairs("BTC", "ETH", days=7, timeframe="1h")

    assert result == {"error": "对比所需行情暂时不完整，请稍后重试"}
