from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any


DEFAULT_STRATEGY_KEY = "ema_rsi_macd"
DEFAULT_TIMEFRAME = "1h"
DEFAULT_RANGE_DAYS = 180
DEFAULT_INITIAL_CASH = 100000.0
DEFAULT_FEE_RATE = 0.1
DEFAULT_HISTORY_MODE = "backtest"

DEFAULT_PORTFOLIO: dict[str, Any] = {
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "max_open_trades": 2,
    "position_size_pct": 25.0,
    "stake_mode": "fixed",
}

DEFAULT_RESEARCH: dict[str, Any] = {
    "slippage_bps": 5.0,
    "funding_rate_daily": 0.0,
    "in_sample_ratio": 100.0,
    "optimize_metric": "sharpe",
    "optimize_trials": 0,
    "rolling_windows": 0,
}

OPTIMIZE_METRIC_OPTIONS: list[dict[str, str]] = [
    {"key": "sharpe", "label": "Sharpe"},
    {"key": "profit_pct", "label": "Profit %"},
    {"key": "calmar", "label": "Calmar"},
    {"key": "profit_factor", "label": "Profit Factor"},
]


def default_backtest_dates(today: date | None = None) -> tuple[date, date]:
    current = today or date.today()
    return current - timedelta(days=DEFAULT_RANGE_DAYS), current


def backtest_run_defaults(today: date | None = None) -> dict[str, Any]:
    start_date, end_date = default_backtest_dates(today)
    return {
        "strategy_key": DEFAULT_STRATEGY_KEY,
        "timeframe": DEFAULT_TIMEFRAME,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "initial_cash": DEFAULT_INITIAL_CASH,
        "fee_rate": DEFAULT_FEE_RATE,
        "portfolio": deepcopy(DEFAULT_PORTFOLIO),
        "research": deepcopy(DEFAULT_RESEARCH),
        "history_mode": DEFAULT_HISTORY_MODE,
        "optimize_metric_options": deepcopy(OPTIMIZE_METRIC_OPTIONS),
    }
