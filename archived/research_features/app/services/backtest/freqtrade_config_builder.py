from __future__ import annotations

from typing import Any

from app.contracts.backtest import BacktestPortfolioConfig
from config import settings


class FreqtradeConfigBuilder:
    def build(
        self,
        *,
        symbols: list[str],
        timeframe: str,
        initial_cash: float,
        portfolio: BacktestPortfolioConfig,
        stake_currency: str,
        market_type: str,
        trade_settings: dict[str, Any],
    ) -> dict[str, Any]:
        if portfolio.stake_mode == "fixed":
            stake_amount: str | float = round(
                initial_cash * portfolio.position_size_pct / 100.0, 8
            )
            tradable_balance_ratio = 0.99
        else:
            stake_amount = "unlimited"
            tradable_balance_ratio = min(
                (portfolio.max_open_trades * portfolio.position_size_pct) / 100.0, 0.99
            )
        config = {
            "$schema": "https://schema.freqtrade.io/schema.json",
            "max_open_trades": portfolio.max_open_trades,
            "stake_currency": stake_currency,
            "stake_amount": stake_amount,
            "tradable_balance_ratio": max(tradable_balance_ratio, 0.01),
            "dry_run": True,
            "dry_run_wallet": initial_cash,
            "cancel_open_orders_on_exit": False,
            "trading_mode": "futures" if market_type == "futures" else "spot",
            "timeframe": timeframe,
            "dataformat_ohlcv": "json",
            "dataformat_trades": "json",
            "order_types": dict(trade_settings["order_types"]),
            "entry_pricing": dict(trade_settings["entry_pricing"]),
            "exit_pricing": dict(trade_settings["exit_pricing"]),
            "exchange": {
                "name": settings.EXCHANGE_ID,
                "key": "",
                "secret": "",
                "password": "",
                "ccxt_config": {},
                "ccxt_async_config": {},
                "pair_whitelist": symbols,
                "pair_blacklist": [],
            },
            "pairlists": [{"method": "StaticPairList"}],
            "bot_name": "heimdall-backtest",
            "internals": {"process_throttle_secs": 5},
        }
        if market_type == "futures":
            config["margin_mode"] = "isolated"
        return config
