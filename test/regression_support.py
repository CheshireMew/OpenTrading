from __future__ import annotations
from app.contracts.market_history import (
    build_market_history_response,
    build_ohlcv_points,
)


def make_kline_data() -> list[list[float]]:
    return [
        [1710000000000, 100.0, 110.0, 95.0, 108.0, 1000.0],
        [1710003600000, 108.0, 112.0, 101.0, 111.0, 1200.0],
        [1710007200000, 111.0, 118.0, 109.0, 116.0, 1300.0],
    ]
























def make_market_realtime_response() -> dict:
    return {
        "symbol": "BTC/USDT",
        "timestamp": "2025-06-01T12:00:00",
        "current_price": 116.0,
        "indicators": {
            "ema": 110.5,
            "rsi": 61.2,
            "macd": {"dif": 1.2, "dea": 0.8, "histogram": 0.4},
            "atr": 5.3,
            "atr_pct": 0.045,
            "realized_volatility_pct": 0.13,
            "annualized_volatility_pct": 0.44,
        },
        "ai_analysis": {"signal": "BUY", "confidence": 78},
        "kline_data": build_ohlcv_points(make_kline_data()),
        "timeframe": "1h",
        "type": "snapshot",
    }


def make_market_indicator() -> dict:
    return {
        "indicator_id": "FEAR_GREED",
        "name": "Fear & Greed",
        "category": "Sentiment",
        "unit": "index",
        "current_value": 72.0,
        "last_updated": "2025-06-01T12:00:00",
        "history": [{"date": "2025-05-31", "value": 68.0}],
    }


def make_binance_breakout_monitor_response() -> dict:
    return {
        "exchange": "binance",
        "min_rise_pct": 5.0,
        "quote_asset": "USDT",
        "updated_at": 1717243200000,
        "summary": {
            "monitored_count": 2,
            "natural_count": 2,
            "momentum_count": 1,
            "focus_count": 1,
            "advancing_count": 1,
            "spot_count": 1,
            "contract_count": 1,
        },
        "items": [
            {
                "market": "spot",
                "market_label": "现货",
                "symbol": "DOGEUSDT",
                "last_price": 0.164,
                "mark_price": None,
                "price_change_pct": 8.6,
                "quote_volume": 310000000.0,
                "funding_rate_pct": None,
                "change_15m_pct": 0.9,
                "change_1h_pct": 2.3,
                "change_4h_pct": 5.7,
                "pullback_from_high_pct": -1.1,
                "range_position_pct": 88.0,
                "ema20_gap_15m_pct": 1.8,
                "ema20_gap_1h_pct": 4.2,
                "rsi_15m": 63.0,
                "rsi_1h": 66.0,
                "macd_hist_15m": 0.004,
                "green_ratio_15m_pct": 66.0,
                "natural_score": 82,
                "momentum_score": 84,
                "structure_ok": True,
                "momentum_ok": True,
                "follow_status": "继续上行",
                "verdict": "优先关注",
                "reasons": ["离高点不远，回撤不深", "15 分钟仍站在均线之上"],
            },
            {
                "market": "usdm",
                "market_label": "U 本位",
                "symbol": "SUIUSDT",
                "last_price": 1.82,
                "mark_price": 1.81,
                "price_change_pct": 6.2,
                "quote_volume": 180000000.0,
                "funding_rate_pct": 0.012,
                "change_15m_pct": -0.2,
                "change_1h_pct": 0.5,
                "change_4h_pct": 3.1,
                "pullback_from_high_pct": -2.9,
                "range_position_pct": 71.0,
                "ema20_gap_15m_pct": 0.5,
                "ema20_gap_1h_pct": 2.1,
                "rsi_15m": 57.0,
                "rsi_1h": 59.0,
                "macd_hist_15m": 0.001,
                "green_ratio_15m_pct": 58.0,
                "natural_score": 71,
                "momentum_score": 62,
                "structure_ok": True,
                "momentum_ok": False,
                "follow_status": "高位蓄势",
                "verdict": "继续跟踪",
                "reasons": ["价格仍压在强势区间上沿"],
            },
        ],
    }


def make_trade_setup_response() -> dict:
    return {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "timestamp": "2025-06-01T12:00:00",
        "current_price": 116.0,
        "setup": {
            "side": "long",
            "entry": 116.0,
            "target": 126.6,
            "stop": 110.7,
            "risk_reward": 2.0,
            "confidence": 85,
            "risk_amount": 10.0,
            "entry_time": 1710007200000,
            "style": "Scalping",
            "strategy": "最大收益",
            "source": "rules",
        },
        "reason": "做多：价格站上EMA，MACD 偏强，RSI 61.2",
        "source": "rules",
        "status": "ready",
        "error_code": None,
    }


class StubMarketQueryAppService:
    valid_symbols = ["BTC/USDT", "ETH/USDT"]
    valid_timeframes = ["1h", "4h", "1d"]
    full_history_used_external_persist_callback = False

    async def get_realtime(self, **kwargs):
        return make_market_realtime_response()

    async def get_current_price(self, **kwargs):
        return {
            "symbol": kwargs.get("symbol", "BTC/USDT"),
            "timeframe": kwargs.get("timeframe", "1d"),
            "timestamp": "2025-06-01T12:00:00",
            "current_price": 68000.0,
        }

    async def get_current_price_batch(self, **kwargs):
        symbols = kwargs.get("symbols", ["BTC/USDT"])
        timeframe = kwargs.get("timeframe", "1d")
        return {
            "timeframe": timeframe,
            "items": [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": "2025-06-01T12:00:00",
                    "current_price": 68000.0 if symbol == "BTC/USDT" else 3500.0,
                    "source": "websocket_snapshot",
                }
                for symbol in symbols
            ],
        }

    async def get_history(self, **kwargs):
        return build_market_history_response(
            symbol=kwargs.get("symbol", "BTC/USDT"),
            timeframe=kwargs.get("timeframe", "1h"),
            rows=make_kline_data(),
        )

    async def get_recent_klines(self, **kwargs):
        return await self.get_history(**kwargs)

    async def get_full_history(self, *, persist_klines=None, **kwargs):
        klines = make_kline_data()
        self.full_history_used_external_persist_callback = persist_klines is not None
        if persist_klines:
            persist_klines(kwargs["symbol"], kwargs["timeframe"], klines)
        return build_market_history_response(
            symbol=kwargs.get("symbol", "BTC/USDT"),
            timeframe=kwargs.get("timeframe", "1h"),
            rows=klines,
        )

    async def get_live_kline_tail(self, **kwargs):
        return {
            "symbol": kwargs.get("symbol", "BTC/USDT"),
            "timeframe": kwargs.get("timeframe", "1h"),
            "timestamp": "2025-06-01T12:00:00",
            "current_price": 116.0,
            "kline_data": build_ohlcv_points(make_kline_data()),
        }


class StubMarketInsightAppService:
    async def get_indicators_async(self, **kwargs):
        return [make_market_indicator()]

    async def get_trade_setup(self, **kwargs):
        return make_trade_setup_response()


class StubBinanceMarketPageService:
    async def get_page(self, **kwargs):
        monitor = make_binance_breakout_monitor_response()
        return {
            "exchange": "binance",
            "quote_asset": monitor["quote_asset"],
            "updated_at": monitor["updated_at"],
            "monitor": monitor,
            "spot_boards": {},
            "contract_boards": {},
            "load_errors": [],
            "refresh_status": {
                "snapshot_ready": True,
                "boards_ready": True,
                "monitor_ready": True,
                "refreshing": False,
                "oi_ready_count": 0,
                "oi_requested_count": 0,
                "last_refresh_started_at": monitor["updated_at"],
                "last_refresh_completed_at": monitor["updated_at"],
                "last_refresh_error": None,
            },
        }


class StubBinanceMarketService:
    def __init__(self) -> None:
        self.page = StubBinanceMarketPageService()


class StubBinanceWeb3RanksService:
    pass


class StubBinanceWeb3HeatRanksService:
    pass


class StubBinanceWeb3TokensService:
    pass






class StubToolsAppService:
    async def simulate_dca(self, command):
        return {
            "symbol": command.symbol,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "target_time": "23:00",
            "total_days": 365,
            "total_invested": 1200.0,
            "final_value": 1480.0,
            "total_coins": 0.02,
            "roi": 23.33,
            "average_cost": 60000.0,
            "profit_loss": 280.0,
            "current_price": 74000.0,
            "data_quality": "exchange",
            "history": [],
            "profit_pct": 23.33,
        }

    async def compare_pairs(self, command):
        return {
            "symbol_a": command.symbol_a,
            "symbol_b": command.symbol_b,
            "data_a": [],
            "data_b": [],
            "ratio_ohlc": [],
            "ratio_symbol": f"{command.symbol_a}/{command.symbol_b}",
            "relative_strength": 1.12,
            "statistics": {
                "aligned_points": 0,
                "symbol_a_return_pct": None,
                "symbol_b_return_pct": None,
                "excess_return_pct": None,
                "return_correlation": None,
                "ratio_change_pct": None,
            },
        }






