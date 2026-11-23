"""Example: compare the last two completed moving-average values."""
from app.domain.local_backtest import Intent

STRATEGY = {'id': 'ma_cross',
 'name': '均线交叉',
 'description': '快线上穿开多，下穿开空；反向信号先平后开。',
 'api_version': '1',
 'warmup_bars': 201,
 'parameters': {'fast': {'type': 'int', 'default': 10, 'min': 2, 'max': 100, 'label': '快线周期', 'unit': '根'},
                'slow': {'type': 'int', 'default': 30, 'min': 3, 'max': 200, 'label': '慢线周期', 'unit': '根'},
                'stop': {'type': 'float', 'default': 5, 'min': 0.01, 'max': 99, 'label': '止损 %', 'unit': '%'},
                'target': {'type': 'float', 'default': 10, 'min': 0.01, 'max': 99, 'label': '止盈 %', 'unit': '%'},
                'trailing': {'type': 'float', 'default': 0, 'min': 0, 'max': 99, 'label': '移动止损 %（0 关闭）', 'unit': '%'}},
 'rules': ['快线上穿开多，下穿开空；反向信号先平后开。'],
 'warmup_rule': {'version': '1',
                 'seed_weight_tolerance': 1e-08,
                 'minimum_bars': 1,
                 'terms': [{'kind': 'window', 'period': 'fast', 'extra_bars': 1, 'enabled_when': []},
                           {'kind': 'window', 'period': 'slow', 'extra_bars': 1, 'enabled_when': []}],
                 'explanation': '按当前参数取各指标所需历史的最大值。EMA／RMA 初始值权重降至 1e-8 以下，再覆盖已声明回看窗口；这是数值初始化标准，不保证价格或信号完全相同。'},
 'parameter_constraints': [{'parameter': 'fast',
                            'operator': 'lt',
                            'other_parameter': 'slow',
                            'message': '快线周期必须小于慢线周期'}]}


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
