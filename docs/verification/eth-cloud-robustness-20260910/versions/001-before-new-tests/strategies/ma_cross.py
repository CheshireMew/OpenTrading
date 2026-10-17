"""Example: compare the last two completed moving-average values."""
from app.domain.local_backtest import Intent

STRATEGY = {
    "id": "ma_cross", "name": "均线交叉", "description": "快线上穿开多，下穿开空；反向信号先平后开。",
    "api_version": "1", "warmup_bars": 201,
    "parameters": {
        "fast": {"type": "int", "default": 10, "min": 2, "max": 100, "label": "快线周期"},
        "slow": {"type": "int", "default": 30, "min": 3, "max": 200, "label": "慢线周期"},
        "stop": {"type": "float", "default": 5, "min": 0.01, "max": 99, "label": "止损 %"},
        "target": {"type": "float", "default": 10, "min": 0.01, "max": 99, "label": "止盈 %"},
        "trailing": {"type": "float", "default": 0, "min": 0, "max": 99, "label": "移动止损 %（0 关闭）"},
    },
}


def on_bar(context):
    p, h = context.parameters, context.history
    if p["fast"] >= p["slow"]:
        raise ValueError("快线周期必须小于慢线周期")
    def average(period, offset):
        end = len(h) - offset
        return sum(h[j].close for j in range(end - period, end)) / period
    previous = average(p["fast"], 1) - average(p["slow"], 1)
    current = average(p["fast"], 0) - average(p["slow"], 0)
    action = "long" if previous <= 0 < current else "short" if previous >= 0 > current else "hold"
    return Intent(action, p["stop"], p["target"], p["trailing"] or None, "均线交叉")
