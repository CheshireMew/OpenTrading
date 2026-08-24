from __future__ import annotations

from app.services.backtest.freqtrade_config_builder import FreqtradeConfigBuilder
from app.services.backtest.freqtrade_strategy_builder import FreqtradeStrategyBuilder
from app.contracts.backtest import BacktestPortfolioConfig
from app.domain.backtest.strategy_rule_tree import build_condition, build_group


def test_freqtrade_config_uses_same_side_pricing_for_spot_and_futures():
    config_builder = FreqtradeConfigBuilder()
    strategy_builder = FreqtradeStrategyBuilder("HeimdallStrategy")
    portfolio = BacktestPortfolioConfig(
        symbols=["BTC/USDT"],
        max_open_trades=2,
        position_size_pct=25,
        stake_mode="fixed",
    )
    trade_settings = strategy_builder.trade_settings("ema_rsi_macd", {})

    spot_config = config_builder.build(
        symbols=["BTC/USDT"],
        timeframe="1h",
        initial_cash=10000,
        portfolio=portfolio,
        stake_currency="USDT",
        market_type="spot",
        trade_settings=trade_settings,
    )
    futures_config = config_builder.build(
        symbols=["BTC/USDT:USDT"],
        timeframe="1h",
        initial_cash=10000,
        portfolio=portfolio,
        stake_currency="USDT",
        market_type="futures",
        trade_settings=trade_settings,
    )

    assert spot_config["order_types"]["entry"] == "market"
    assert spot_config["order_types"]["exit"] == "market"
    assert spot_config["entry_pricing"]["price_side"] == "other"
    assert spot_config["exit_pricing"]["price_side"] == "other"
    assert spot_config["entry_pricing"]["use_order_book"] is True
    assert spot_config["exit_pricing"]["use_order_book"] is True
    assert futures_config["entry_pricing"]["price_side"] == "other"
    assert futures_config["exit_pricing"]["price_side"] == "other"
    assert futures_config["entry_pricing"]["use_order_book"] is True
    assert futures_config["exit_pricing"]["use_order_book"] is True
    assert futures_config["trading_mode"] == "futures"
    assert futures_config["margin_mode"] == "isolated"


def test_freqtrade_codegen_does_not_compile_inactive_signal_groups_as_always_true():
    strategy_builder = FreqtradeStrategyBuilder("HeimdallStrategy")
    config = {
        "indicators": {},
        "execution": {"market_type": "futures", "direction": "long_short"},
        "regime_priority": ["trend", "range"],
        "trend": {
            "enabled": True,
            "regime": build_group("trend_regime", "趋势状态", "and", []),
            "long_entry": build_group(
                "trend_long_entry",
                "趋势做多入场",
                "and",
                [
                    build_condition(
                        "close_gt_100",
                        "收盘价高于 100",
                        {"kind": "price", "field": "close"},
                        "gt",
                        {"kind": "value", "value": 100},
                    )
                ],
            ),
            "long_exit": build_group("trend_long_exit", "趋势做多离场", "or", [], enabled=False),
            "short_entry": build_group("trend_short_entry", "趋势做空入场", "and", [], enabled=False),
            "short_exit": build_group("trend_short_exit", "趋势做空离场", "or", [], enabled=False),
        },
        "range": {"enabled": False},
    }

    code = strategy_builder.build_code("ema_rsi_macd", "1h", config)

    assert "trend_long_entry" in code
    assert "trend_long_exit" not in code
    assert "trend_short_entry" not in code
    assert "trend_short_exit" not in code
