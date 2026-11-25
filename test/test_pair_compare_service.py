from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.contracts.dto.market_catalog import MarketIndexHistoryResponse
from app.contracts.market_history import build_ohlcv_points
from app.services.tools.pair_compare_service import PairCompareService
from app.services.market.history_range_coordinator import OhlcvRangeResult


@pytest.mark.parametrize(
    ("timeframe", "dates"),
    [("1w", ["2024-01-29"]), ("1M", ["2024-01-01", "2024-02-01"])],
    ids=["monday-week", "calendar-month"],
)
def test_compare_calendar_buckets_cross_february(timeframe, dates):
    start = datetime(2024, 1, 31, tzinfo=timezone.utc)
    rows = [
        [int((start + timedelta(minutes=5 * i)).timestamp() * 1000), 100, 102, 99, 101, 1]
        for i in range(3 * 24 * 12)
    ]
    market = MagicMock()
    service = PairCompareService(market, MagicMock())
    native_rows = service._aggregate_klines(rows, timeframe)
    market.load_ohlcv_range.return_value = OhlcvRangeResult(native_rows, [])

    result = service.compare_pairs("BTC", "ETH", days=3, timeframe=timeframe)

    assert "error" not in result
    actual = [datetime.fromtimestamp(row["time"], timezone.utc).strftime("%Y-%m-%d") for row in result["data_a"]]
    assert actual == dates
    assert [row["time"] for row in result["data_b"]] == [row["time"] for row in result["data_a"]]
    assert result["statistics"]["aligned_points"] == len(dates)
    assert [call.args[1] for call in market.load_ohlcv_range.call_args_list] == [timeframe, timeframe]


def test_compare_index_symbols_uses_index_history():
    index_service = MagicMock()
    index_service.get_instrument.side_effect = lambda symbol: object() if symbol in {"HK_HSI", "US_SP500"} else None
    index_service.get_history.side_effect = lambda **kwargs: MarketIndexHistoryResponse(
            coverage={"complete": True, "calendar": "XHKG", "start_date": "2024-01-02", "end_date": "2024-01-04"},
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
        now=datetime(2026, 8, 24, 10, 7, 42, tzinfo=timezone.utc),
    )

    assert end == datetime(2026, 8, 24, 10, 5, tzinfo=timezone.utc)
    assert start == datetime(2026, 8, 17, 10, 5, tzinfo=timezone.utc)
    assert int(end.timestamp() * 1000) % (5 * 60 * 1000) == 0


def test_native_daily_index_history_excludes_the_current_utc_day():
    indexes = MagicMock()
    indexes.get_history.return_value = MarketIndexHistoryResponse(
        symbol="US_SP500", name="S&P 500", market="US", currency="USD", native_currency="USD",
        timeframe="1d", source="test", price_basis="index", count=0, data=[],
        coverage={"complete": True, "calendar": "XNYS", "start_date": "2026-11-23", "end_date": "2026-11-25"},
    )
    service = PairCompareService(MagicMock(), indexes)
    window = service._closed_history_window(3, "1d", now=datetime(2026, 11, 26, 10, tzinfo=timezone(timedelta(hours=8))))
    service._fetch_history({"asset_class": "index", "symbol": "US_SP500"}, *window, "1d")
    assert indexes.get_history.call_args.kwargs["start_date"] == "2026-11-23"
    assert indexes.get_history.call_args.kwargs["end_date"] == "2026-11-25"


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
