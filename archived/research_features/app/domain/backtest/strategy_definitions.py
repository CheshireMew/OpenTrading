from __future__ import annotations

from typing import Any

from app.domain.market.trade_setup_rules import BACKTEST_FIXED_STRATEGY, BACKTEST_FIXED_STYLE, SIDE_RULES, STRATEGY_PROFILES, STYLE_PROFILES
from app.domain.backtest.strategy_config_normalizer import execution_defaults
from app.domain.backtest.strategy_rule_tree import branch_defaults, build_condition, build_group


_builtin_rule_style = STYLE_PROFILES[BACKTEST_FIXED_STYLE]
_builtin_rule_strategy = STRATEGY_PROFILES[BACKTEST_FIXED_STRATEGY]
_builtin_long_rule = SIDE_RULES["long"]
_builtin_short_rule = SIDE_RULES["short"]

BUILTIN_TEMPLATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "smart_order_builtin_rules": {
        "template": "smart_order_builtin_rules",
        "name": "智能开单计划回测",
        "category": "system",
        "description": "对应智能开单中的内置规则计划版，开仓后固定目标和止损，按单笔交易计划回放。",
        "indicator_keys": ["ema", "rsi", "macd", "atr", "rolling_high", "rolling_low"],
        "config": {
            "indicators": {
                "ema": {"label": "EMA", "type": "ema", "timeframe": "base", "params": {"period": 20}},
                "rsi": {"label": "RSI", "type": "rsi", "timeframe": "base", "params": {"period": 14}},
                "macd": {"label": "MACD", "type": "macd", "timeframe": "base", "params": {"fast": 12, "slow": 26, "signal": 9}},
                "atr": {"label": "ATR", "type": "atr", "timeframe": "base", "params": {"period": 14}},
                "recent_high": {"label": "Recent High", "type": "rolling_high", "timeframe": "base", "params": {"lookback": 20}},
                "recent_low": {"label": "Recent Low", "type": "rolling_low", "timeframe": "base", "params": {"lookback": 20}},
            },
            "execution": {"market_type": "futures", "direction": "long_short"},
            "regime_priority": ["trend", "range"],
            "trend": {
                **branch_defaults("trend", "趋势", enabled=True),
                "long_entry": build_group(
                    "builtin_rule_long_entry",
                    "内置规则做多入场",
                    "and",
                    [
                        build_condition("builtin_rule_long_price_above_ema", "收盘价站上 EMA", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("builtin_rule_long_macd_hist_positive", "MACD Hist 不低于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "gte", {"kind": "value", "value": _builtin_long_rule["macd_hist_threshold"]}),
                        build_condition("builtin_rule_long_rsi_floor", "RSI 不低于下限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "gte", {"kind": "value", "value": _builtin_long_rule["rsi_min"]}),
                        build_condition("builtin_rule_long_rsi_cap", "RSI 不高于上限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lte", {"kind": "value", "value": _builtin_long_rule["rsi_max"]}),
                    ],
                ),
                "long_exit": build_group(
                    "builtin_rule_long_exit",
                    "内置规则做多离场",
                    "or",
                    [
                        build_condition("builtin_rule_long_price_below_ema", "收盘价跌破 EMA", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("builtin_rule_long_macd_hist_negative", "MACD Hist 低于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "lt", {"kind": "value", "value": _builtin_long_rule["macd_hist_threshold"]}),
                    ],
                ),
                "short_entry": build_group(
                    "builtin_rule_short_entry",
                    "内置规则做空入场",
                    "and",
                    [
                        build_condition("builtin_rule_short_price_below_ema", "收盘价跌破 EMA", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("builtin_rule_short_macd_hist_negative", "MACD Hist 不高于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "lte", {"kind": "value", "value": _builtin_short_rule["macd_hist_threshold"]}),
                        build_condition("builtin_rule_short_rsi_floor", "RSI 不低于下限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "gte", {"kind": "value", "value": _builtin_short_rule["rsi_min"]}),
                        build_condition("builtin_rule_short_rsi_cap", "RSI 不高于上限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lte", {"kind": "value", "value": _builtin_short_rule["rsi_max"]}),
                    ],
                    enabled=True,
                ),
                "short_exit": build_group(
                    "builtin_rule_short_exit",
                    "内置规则做空离场",
                    "or",
                    [
                        build_condition("builtin_rule_short_price_above_ema", "收盘价站回 EMA 上方", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("builtin_rule_short_macd_hist_positive", "MACD Hist 高于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "gt", {"kind": "value", "value": _builtin_short_rule["macd_hist_threshold"]}),
                    ],
                    enabled=True,
                ),
            },
            "range": branch_defaults("range", "区间", enabled=False),
            "risk": {
                "stoploss": -0.99,
                "roi_targets": [],
                "trade_plan": {
                    "enabled": True,
                    "stop_multiplier": _builtin_rule_style["stop_multiplier"],
                    "min_stop_pct": _builtin_rule_style["min_stop_pct"],
                    "reward_multiplier": _builtin_rule_strategy["reward_multiplier"],
                    "atr_indicator": "atr",
                    "support_indicator": "recent_low",
                    "resistance_indicator": "recent_high",
                },
                "trailing": {"enabled": False, "positive": 0.02, "offset": 0.03, "only_offset_reached": True},
                "partial_exits": [],
            },
        },
        "parameter_space": {},
        "builtin": {
            "key": "smart_order_builtin_rules",
            "version_name": "固定版 v1",
            "notes": "信号阈值与智能开单内置规则同步，按固定交易计划执行",
        },
    },
    "smart_order_traditional_strategy": {
        "template": "smart_order_traditional_strategy",
        "name": "智能开单传统策略",
        "category": "system",
        "description": "把智能开单的方向判断改写成持续型趋势策略，每根 K 线都重新判断进出场。",
        "indicator_keys": ["ema", "rsi", "macd"],
        "config": {
            "indicators": {
                "ema": {"label": "EMA", "type": "ema", "timeframe": "base", "params": {"period": 20}},
                "rsi": {"label": "RSI", "type": "rsi", "timeframe": "base", "params": {"period": 14}},
                "macd": {"label": "MACD", "type": "macd", "timeframe": "base", "params": {"fast": 12, "slow": 26, "signal": 9}},
            },
            "execution": {"market_type": "futures", "direction": "long_short"},
            "regime_priority": ["trend", "range"],
            "trend": {
                **branch_defaults("trend", "趋势", enabled=True),
                "long_entry": build_group(
                    "smart_traditional_long_entry",
                    "传统策略做多入场",
                    "and",
                    [
                        build_condition("smart_traditional_long_price_above_ema", "收盘价站上 EMA", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("smart_traditional_long_macd_hist_positive", "MACD Hist 不低于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "gte", {"kind": "value", "value": _builtin_long_rule["macd_hist_threshold"]}),
                        build_condition("smart_traditional_long_rsi_floor", "RSI 不低于下限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "gte", {"kind": "value", "value": _builtin_long_rule["rsi_min"]}),
                        build_condition("smart_traditional_long_rsi_cap", "RSI 不高于上限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lte", {"kind": "value", "value": _builtin_long_rule["rsi_max"]}),
                    ],
                ),
                "long_exit": build_group(
                    "smart_traditional_long_exit",
                    "传统策略做多离场",
                    "or",
                    [
                        build_condition("smart_traditional_long_price_below_ema", "收盘价跌破 EMA", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("smart_traditional_long_macd_hist_negative", "MACD Hist 低于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "lt", {"kind": "value", "value": _builtin_long_rule["macd_hist_threshold"]}),
                        build_condition("smart_traditional_long_rsi_overheat", "RSI 高于上限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "gt", {"kind": "value", "value": _builtin_long_rule["rsi_max"]}),
                    ],
                ),
                "short_entry": build_group(
                    "smart_traditional_short_entry",
                    "传统策略做空入场",
                    "and",
                    [
                        build_condition("smart_traditional_short_price_below_ema", "收盘价跌破 EMA", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("smart_traditional_short_macd_hist_negative", "MACD Hist 不高于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "lte", {"kind": "value", "value": _builtin_short_rule["macd_hist_threshold"]}),
                        build_condition("smart_traditional_short_rsi_floor", "RSI 不低于下限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "gte", {"kind": "value", "value": _builtin_short_rule["rsi_min"]}),
                        build_condition("smart_traditional_short_rsi_cap", "RSI 不高于上限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lte", {"kind": "value", "value": _builtin_short_rule["rsi_max"]}),
                    ],
                    enabled=True,
                ),
                "short_exit": build_group(
                    "smart_traditional_short_exit",
                    "传统策略做空离场",
                    "or",
                    [
                        build_condition("smart_traditional_short_price_above_ema", "收盘价站回 EMA 上方", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("smart_traditional_short_macd_hist_positive", "MACD Hist 高于 0", {"kind": "indicator", "indicator": "macd", "output": "hist"}, "gt", {"kind": "value", "value": _builtin_short_rule["macd_hist_threshold"]}),
                        build_condition("smart_traditional_short_rsi_exhausted", "RSI 低于下限", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lt", {"kind": "value", "value": _builtin_short_rule["rsi_min"]}),
                    ],
                    enabled=True,
                ),
            },
            "range": branch_defaults("range", "区间", enabled=False),
            "risk": {
                "stoploss": -0.02,
                "roi_targets": [{"id": "roi_0", "minutes": 0, "profit": 0.048, "enabled": True}],
                "trailing": {"enabled": False, "positive": 0.02, "offset": 0.03, "only_offset_reached": True},
                "partial_exits": [],
            },
        },
        "parameter_space": {},
        "builtin": {
            "key": "smart_order_traditional_strategy",
            "version_name": "传统版 v1",
            "notes": "保留智能开单方向过滤，但改为持续型进出场策略",
        },
    },
    "ema_rsi_macd": {
        "template": "ema_rsi_macd",
        "name": "EMA RSI MACD",
        "category": "trend",
        "description": "经典趋势跟随模板，结合 EMA 趋势、RSI 过滤和 MACD 动量确认。",
        "indicator_keys": ["ema", "sma", "rsi", "macd", "atr", "roc"],
        "config": {
            "indicators": {
                "ema": {"label": "EMA", "type": "ema", "timeframe": "base", "params": {"period": 20}},
                "rsi": {"label": "RSI", "type": "rsi", "timeframe": "base", "params": {"period": 14}},
                "macd": {"label": "MACD", "type": "macd", "timeframe": "base", "params": {"fast": 12, "slow": 26, "signal": 9}},
            },
            "execution": execution_defaults(),
            "regime_priority": ["trend", "range"],
            "trend": {
                **branch_defaults("trend", "趋势", enabled=True),
                "long_entry": build_group(
                    "trend_long_entry",
                    "趋势做多入场",
                    "and",
                    [
                        build_condition("price_above_ema", "收盘价站上 EMA", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("entry_rsi_max", "RSI 低于入场阈值", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lt", {"kind": "value", "value": 68}),
                        build_condition("macd_confirmation", "MACD 高于信号线", {"kind": "indicator", "indicator": "macd", "output": "macd"}, "gt", {"kind": "indicator", "indicator": "macd", "output": "signal"}),
                    ],
                ),
                "long_exit": build_group(
                    "trend_long_exit",
                    "趋势做多离场",
                    "or",
                    [
                        build_condition("price_below_ema", "收盘价跌破 EMA", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "ema", "output": "value"}),
                        build_condition("exit_rsi_min", "RSI 低于离场阈值", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lt", {"kind": "value", "value": 32}),
                    ],
                ),
            },
            "range": branch_defaults("range", "区间", enabled=False),
            "risk": {
                "stoploss": -0.12,
                "roi_targets": [{"id": "roi_0", "minutes": 0, "profit": 0.09, "enabled": True}, {"id": "roi_1", "minutes": 180, "profit": 0.04, "enabled": True}],
                "trailing": {"enabled": True, "positive": 0.02, "offset": 0.04, "only_offset_reached": True},
                "partial_exits": [{"id": "partial_1", "profit": 0.05, "size_pct": 35, "enabled": True}, {"id": "partial_2", "profit": 0.09, "size_pct": 25, "enabled": True}],
            },
        },
        "parameter_space": {
            "indicators.ema.params.period": [10, 20, 30, 50],
            "trend.long_entry.entry_rsi_max.right.value": [60, 65, 68, 72],
            "trend.long_exit.exit_rsi_min.right.value": [28, 32, 35, 40],
            "risk.trailing.positive": [0.015, 0.02, 0.03],
        },
        "builtin": {"key": "ema_rsi_macd", "version_name": "Base v1", "notes": "默认趋势跟随版本"},
    },
    "bbands_mean_reversion": {
        "template": "bbands_mean_reversion",
        "name": "Bollinger Mean Reversion",
        "category": "mean_reversion",
        "description": "布林带均值回归模板，用 RSI 过滤超卖与回归离场。",
        "indicator_keys": ["bbands", "rsi", "atr", "roc", "rolling_low"],
        "config": {
            "indicators": {
                "bbands": {"label": "BBands", "type": "bbands", "timeframe": "base", "params": {"period": 20, "stddev": 2.0}},
                "rsi": {"label": "RSI", "type": "rsi", "timeframe": "base", "params": {"period": 14}},
            },
            "execution": execution_defaults(),
            "regime_priority": ["trend", "range"],
            "trend": branch_defaults("trend", "趋势", enabled=False),
            "range": {
                **branch_defaults("range", "区间", enabled=True),
                "long_entry": build_group(
                    "range_long_entry",
                    "区间做多入场",
                    "and",
                    [
                        build_condition("price_below_lower_band", "收盘价跌破布林下轨", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "bbands", "output": "lower"}),
                        build_condition("entry_rsi_max", "RSI 低于入场阈值", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "lt", {"kind": "value", "value": 35}),
                    ],
                ),
                "long_exit": build_group(
                    "range_long_exit",
                    "区间做多离场",
                    "or",
                    [
                        build_condition("price_above_middle_band", "收盘价回到布林中轨上方", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "bbands", "output": "middle"}),
                        build_condition("exit_rsi_min", "RSI 高于离场阈值", {"kind": "indicator", "indicator": "rsi", "output": "value"}, "gt", {"kind": "value", "value": 60}),
                    ],
                ),
            },
            "risk": {
                "stoploss": -0.08,
                "roi_targets": [{"id": "roi_0", "minutes": 0, "profit": 0.06, "enabled": True}, {"id": "roi_1", "minutes": 120, "profit": 0.03, "enabled": True}],
                "trailing": {"enabled": False, "positive": 0.02, "offset": 0.03, "only_offset_reached": True},
                "partial_exits": [],
            },
        },
        "parameter_space": {
            "indicators.bbands.params.period": [14, 20, 26],
            "indicators.bbands.params.stddev": [1.8, 2.0, 2.2],
            "range.long_entry.entry_rsi_max.right.value": [28, 32, 35, 40],
        },
        "builtin": {"key": "bbands_mean_reversion", "version_name": "Base v1", "notes": "震荡市值回归版本"},
    },
    "breakout_volume": {
        "template": "breakout_volume",
        "name": "Breakout Volume",
        "category": "breakout",
        "description": "通道突破模板，结合成交量放大和 ATR 跟踪止损。",
        "indicator_keys": ["rolling_high", "rolling_low", "volume_sma", "atr", "roc", "ema"],
        "config": {
            "indicators": {
                "breakout_high": {"label": "Breakout High", "type": "rolling_high", "timeframe": "base", "params": {"lookback": 20}},
                "volume_sma": {"label": "Volume SMA", "type": "volume_sma", "timeframe": "base", "params": {"period": 20}},
                "atr": {"label": "ATR", "type": "atr", "timeframe": "base", "params": {"period": 14}},
            },
            "execution": execution_defaults(),
            "regime_priority": ["trend", "range"],
            "trend": {
                **branch_defaults("trend", "趋势", enabled=True),
                "long_entry": build_group(
                    "trend_long_entry",
                    "趋势做多入场",
                    "and",
                    [
                        build_condition("price_above_breakout_high", "收盘价突破高点", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "breakout_high", "output": "value"}),
                        build_condition("volume_above_multiplier", "成交量大于量均线乘数", {"kind": "price", "field": "volume"}, "gt", {"kind": "indicator_multiplier", "indicator": "volume_sma", "output": "value", "multiplier": 1.5}),
                    ],
                ),
                "long_exit": build_group(
                    "trend_long_exit",
                    "趋势做多离场",
                    "or",
                    [
                        build_condition("price_below_atr_stop", "收盘价跌破 ATR 止损", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator_offset", "base_indicator": "breakout_high", "base_output": "value", "offset_indicator": "atr", "offset_output": "value", "offset_multiplier": 2.5}),
                    ],
                ),
            },
            "range": branch_defaults("range", "区间", enabled=False),
            "risk": {
                "stoploss": -0.10,
                "roi_targets": [{"id": "roi_0", "minutes": 0, "profit": 0.12, "enabled": True}, {"id": "roi_1", "minutes": 240, "profit": 0.05, "enabled": True}],
                "trailing": {"enabled": True, "positive": 0.03, "offset": 0.05, "only_offset_reached": True},
                "partial_exits": [{"id": "partial_1", "profit": 0.08, "size_pct": 30, "enabled": True}],
            },
        },
        "parameter_space": {
            "indicators.breakout_high.params.lookback": [10, 20, 30],
            "trend.long_entry.volume_above_multiplier.right.multiplier": [1.2, 1.5, 1.8, 2.0],
            "trend.long_exit.price_below_atr_stop.right.offset_multiplier": [1.5, 2.0, 2.5, 3.0],
            "risk.trailing.offset": [0.04, 0.05, 0.06],
        },
        "builtin": {"key": "breakout_volume", "version_name": "Base v1", "notes": "突破追踪版本"},
    },
    "btc_regime_switch": {
        "template": "btc_regime_switch",
        "name": "BTC Regime Switch",
        "category": "regime",
        "description": "基于 M/E/P 状态源先判趋势或区间，再把 1H 状态、15M 结构和 5M 执行拆开的 BTC 多周期模板。",
        "indicator_keys": ["ema", "rsi", "atr", "displacement_atr", "efficiency_ratio", "range_context"],
        "config": {
            "indicators": {
                "ema_1h": {"label": "1H EMA", "type": "ema", "timeframe": "1h", "params": {"period": 55}},
                "m_1h": {"label": "1H M", "type": "displacement_atr", "timeframe": "1h", "params": {"lookback": 24, "atr_period": 14}},
                "e_1h": {"label": "1H E", "type": "efficiency_ratio", "timeframe": "1h", "params": {"lookback": 24}},
                "range_15m": {"label": "15M Range", "type": "range_context", "timeframe": "15m", "params": {"lookback": 32, "atr_period": 14}},
                "rsi_5m": {"label": "5M RSI", "type": "rsi", "timeframe": "5m", "params": {"period": 14}},
                "atr_5m": {"label": "5M ATR", "type": "atr", "timeframe": "5m", "params": {"period": 14}},
            },
            "execution": {"market_type": "futures", "direction": "long_short"},
            "regime_priority": ["trend", "range"],
            "trend": {
                **branch_defaults("trend", "趋势", enabled=True),
                "regime": build_group(
                    "trend_regime",
                    "趋势状态",
                    "or",
                    [
                        build_group(
                            "trend_regime_up",
                            "上升趋势",
                            "and",
                            [
                                build_condition("trend_up_m", "1H M 高于 2.5", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "gt", {"kind": "value", "value": 2.5}),
                                build_condition("trend_up_e", "1H E 高于 0.35", {"kind": "indicator", "indicator": "e_1h", "output": "value"}, "gt", {"kind": "value", "value": 0.35}),
                            ],
                        ),
                        build_group(
                            "trend_regime_down",
                            "下降趋势",
                            "and",
                            [
                                build_condition("trend_down_m", "1H M 低于 -2.5", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "lt", {"kind": "value", "value": -2.5}),
                                build_condition("trend_down_e", "1H E 高于 0.35", {"kind": "indicator", "indicator": "e_1h", "output": "value"}, "gt", {"kind": "value", "value": 0.35}),
                            ],
                        ),
                    ],
                ),
                "long_entry": build_group(
                    "trend_long_entry",
                    "趋势做多入场",
                    "and",
                    [
                        build_condition("trend_long_m_positive", "1H M 仍为正", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "gt", {"kind": "value", "value": 0.0}),
                        build_condition("trend_long_structure_pullback", "15M P 不高于 0.55", {"kind": "indicator", "indicator": "range_15m", "output": "position"}, "lt", {"kind": "value", "value": 0.55}),
                        build_condition("trend_long_pullback", "收盘价高于 1H EMA 减 0.8ATR", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator_offset", "base_indicator": "ema_1h", "base_output": "value", "offset_indicator": "atr_5m", "offset_output": "value", "offset_multiplier": 0.8}),
                        build_condition("trend_long_rsi", "5M RSI 高于 52", {"kind": "indicator", "indicator": "rsi_5m", "output": "value"}, "gt", {"kind": "value", "value": 52}),
                    ],
                ),
                "long_exit": build_group(
                    "trend_long_exit",
                    "趋势做多离场",
                    "or",
                    [
                        build_condition("trend_long_close_below_ema", "收盘价跌回 1H EMA 下方", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "ema_1h", "output": "value"}),
                        build_condition("trend_long_m_turn", "1H M 跌回 0 下方", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "lt", {"kind": "value", "value": 0}),
                    ],
                ),
                "short_entry": build_group(
                    "trend_short_entry",
                    "趋势做空入场",
                    "and",
                    [
                        build_condition("trend_short_m_negative", "1H M 仍为负", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "lt", {"kind": "value", "value": 0.0}),
                        build_condition("trend_short_structure_pullback", "15M P 不低于 0.45", {"kind": "indicator", "indicator": "range_15m", "output": "position"}, "gt", {"kind": "value", "value": 0.45}),
                        build_condition("trend_short_pullback", "收盘价低于 1H EMA 加 0.8ATR", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator_offset", "base_indicator": "ema_1h", "base_output": "value", "offset_indicator": "atr_5m", "offset_output": "value", "offset_multiplier": -0.8}),
                        build_condition("trend_short_rsi", "5M RSI 低于 48", {"kind": "indicator", "indicator": "rsi_5m", "output": "value"}, "lt", {"kind": "value", "value": 48}),
                    ],
                    enabled=True,
                ),
                "short_exit": build_group(
                    "trend_short_exit",
                    "趋势做空离场",
                    "or",
                    [
                        build_condition("trend_short_close_above_ema", "收盘价站回 1H EMA 上方", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "ema_1h", "output": "value"}),
                        build_condition("trend_short_m_turn", "1H M 回到 0 上方", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "gt", {"kind": "value", "value": 0}),
                    ],
                    enabled=True,
                ),
            },
            "range": {
                **branch_defaults("range", "区间", enabled=True),
                "regime": build_group(
                    "range_regime",
                    "区间状态",
                    "and",
                    [
                        build_condition("range_m_ceiling", "1H M 不高于 1.2", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "lt", {"kind": "value", "value": 1.2}),
                        build_condition("range_m_floor", "1H M 不低于 -1.2", {"kind": "indicator", "indicator": "m_1h", "output": "value"}, "gt", {"kind": "value", "value": -1.2}),
                        build_condition("range_e_cap", "1H E 不高于 0.25", {"kind": "indicator", "indicator": "e_1h", "output": "value"}, "lt", {"kind": "value", "value": 0.25}),
                        build_condition("range_inside_upper", "15M P 不高于 1", {"kind": "indicator", "indicator": "range_15m", "output": "position"}, "lt", {"kind": "value", "value": 1.0}),
                        build_condition("range_inside_lower", "15M P 不低于 0", {"kind": "indicator", "indicator": "range_15m", "output": "position"}, "gt", {"kind": "value", "value": 0.0}),
                        build_condition("range_min_width", "15M 区间宽度至少为 2 倍 ATR", {"kind": "indicator", "indicator": "range_15m", "output": "width_ratio"}, "gt", {"kind": "value", "value": 2.0}),
                    ],
                ),
                "long_entry": build_group(
                    "range_long_entry",
                    "区间假跌破收回后低买",
                    "and",
                    [
                        build_condition("range_long_position", "15M P 不高于 0.15", {"kind": "indicator", "indicator": "range_15m", "output": "position"}, "lt", {"kind": "value", "value": 0.15}),
                        build_condition("range_long_prev_break", "上一根 5M 最低价跌破 15M 下沿", {"kind": "price", "field": "low", "bars_ago": 1}, "lt", {"kind": "indicator", "indicator": "range_15m", "output": "lower", "bars_ago": 1}),
                        build_condition("range_long_rsi_turn", "当前 5M RSI 高于上一根", {"kind": "indicator", "indicator": "rsi_5m", "output": "value"}, "gt", {"kind": "indicator", "indicator": "rsi_5m", "output": "value", "bars_ago": 1}),
                    ],
                ),
                "long_exit": build_group(
                    "range_long_exit",
                    "区间做多离场",
                    "or",
                    [
                        build_condition("range_long_back_to_mid", "收盘价回到 15M 中轴上方", {"kind": "price", "field": "close"}, "gt", {"kind": "indicator", "indicator": "range_15m", "output": "middle"}),
                        build_condition("range_long_rsi_recover", "5M RSI 高于 55", {"kind": "indicator", "indicator": "rsi_5m", "output": "value"}, "gt", {"kind": "value", "value": 55}),
                    ],
                ),
                "short_entry": build_group(
                    "range_short_entry",
                    "区间假突破收回后高空",
                    "and",
                    [
                        build_condition("range_short_position", "15M P 不低于 0.85", {"kind": "indicator", "indicator": "range_15m", "output": "position"}, "gt", {"kind": "value", "value": 0.85}),
                        build_condition("range_short_prev_break", "上一根 5M 最高价突破 15M 上沿", {"kind": "price", "field": "high", "bars_ago": 1}, "gt", {"kind": "indicator", "indicator": "range_15m", "output": "upper", "bars_ago": 1}),
                        build_condition("range_short_rsi_turn", "当前 5M RSI 低于上一根", {"kind": "indicator", "indicator": "rsi_5m", "output": "value"}, "lt", {"kind": "indicator", "indicator": "rsi_5m", "output": "value", "bars_ago": 1}),
                    ],
                    enabled=True,
                ),
                "short_exit": build_group(
                    "range_short_exit",
                    "区间做空离场",
                    "or",
                    [
                        build_condition("range_short_back_to_mid", "收盘价跌回 15M 中轴下方", {"kind": "price", "field": "close"}, "lt", {"kind": "indicator", "indicator": "range_15m", "output": "middle"}),
                        build_condition("range_short_rsi_recover", "5M RSI 低于 45", {"kind": "indicator", "indicator": "rsi_5m", "output": "value"}, "lt", {"kind": "value", "value": 45}),
                    ],
                    enabled=True,
                ),
            },
            "risk": {
                "stoploss": -0.05,
                "roi_targets": [],
                "trailing": {"enabled": False, "positive": 0.01, "offset": 0.02, "only_offset_reached": True},
                "partial_exits": [],
            },
        },
        "parameter_space": {
            "indicators.ema_1h.params.period": [34, 55, 89],
            "indicators.m_1h.params.lookback": [18, 24, 30],
            "indicators.range_15m.params.lookback": [24, 32, 36],
            "trend.regime.trend_regime_up.trend_up_m.right.value": [2.0, 2.5, 3.0],
            "trend.regime.trend_regime_up.trend_up_e.right.value": [0.3, 0.35, 0.4],
            "trend.long_entry.trend_long_pullback.right.offset_multiplier": [0.5, 0.8, 1.0, 1.2],
            "range.regime.range_min_width.right.value": [1.5, 2.0, 2.5, 3.0],
            "range.long_entry.range_long_position.right.value": [0.1, 0.15, 0.2],
            "range.short_entry.range_short_position.right.value": [0.8, 0.85, 0.9],
        },
        "builtin": {"key": "btc_regime_switch", "version_name": "Base v3", "notes": "BTC 多周期 M/E/P 状态切换与假突破收回确认版本"},
    },
    "btc_regime_pulse_supertrend": {
        "template": "btc_regime_pulse_supertrend",
        "name": "BTC Regime Pulse SuperTrend",
        "category": "regime",
        "description": "面向 BTC 的脚本化内置策略，使用状态判定、自适应 SuperTrend 和信号评分一起筛选翻转入场。",
        "indicator_keys": [],
        "config": {
            "indicators": {},
            "execution": {"market_type": "futures", "direction": "long_short"},
            "regime_priority": ["trend", "range"],
            "trend": branch_defaults("trend", "趋势", enabled=False),
            "range": branch_defaults("range", "区间", enabled=False),
            "risk": {
                "stoploss": -0.99,
                "roi_targets": [],
                "trailing": {"enabled": False, "positive": 0.02, "offset": 0.03, "only_offset_reached": True},
                "partial_exits": [],
            },
        },
        "parameter_space": {},
        "builtin": {
            "key": "btc_regime_pulse_supertrend",
            "version_name": "Pulse v1",
            "notes": "AI 评分、自适应 SuperTrend、ATR 止损和固定 RR 止盈的首个内置版本",
        },
    },
}

