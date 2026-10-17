"""Versioned, bounded entry-method experiments; execution remains engine v4."""
from collections import deque
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud

STRATEGY = {
    'id': 'trend_cloud_robustness_v1', 'name': '趋势通道稳健性研究 v1（研究用）',
    'description': '保留利润保护或反向信号退出。单独测试慢趋势过滤、震荡过滤、入场间隔和禁止同向重复入场；旧策略单独保留。',
    'api_version': '1', 'warmup_bars': 650,
    'parameters': {
        'center_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 200, 'label': '中心线 EMA 周期'},
        'width_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 100, 'label': '高低差 EMA 周期'},
        'trigger_mult': {'type': 'float', 'default': .8, 'min': .1, 'max': 1.9, 'label': '交易门槛距离 / 宽度'},
        'activation_pct': {'type': 'float', 'default': 2, 'min': 0, 'max': 20, 'label': '浮盈多少 % 启动保护，0 关闭'},
        'giveback_pct': {'type': 'float', 'default': 50, 'min': 1, 'max': 99, 'label': '最高浮盈允许回吐 %'},
        'entry_method': {'type': 'str', 'default': 'none', 'label': '入场方法：none / slow_trend / efficiency / spacing / alternate'},
        'method_value': {'type': 'float', 'default': 0, 'min': 0, 'max': 200, 'label': '过滤参数（按所选方法解释）'},
        'record_indicators': {'type': 'bool', 'default': True, 'label': '保存云带和入场条件'},
    },
}


class Calculation:
    def __init__(self, p):
        self.p, self.processed = p, 0
        self.base = self.width = self.pc = self.upper = self.lower = self.slow = None
        self.closes = deque(maxlen=33)
        self.last_entry_index = self.last_entry_side = None
        method, value = p['entry_method'], p['method_value']
        if method not in ('none', 'slow_trend', 'efficiency', 'spacing', 'alternate'):
            raise ValueError('未知入场方法')
        if method == 'slow_trend' and (value < 2 or value != int(value)):
            raise ValueError('慢趋势周期必须为至少 2 的整数')
        if method == 'efficiency' and not 0 < value < 1:
            raise ValueError('趋势效率门槛必须介于 0 和 1')
        if method == 'spacing' and (value < 1 or value != int(value)):
            raise ValueError('入场间隔必须为正整数根数')

    def update(self, bar, position=None, decisions=True):
        p, index = self.p, self.processed
        src = (bar.high+bar.low)/2
        self.base = src if self.base is None else self.base+2/(p['center_length']+1)*(src-self.base)
        movement = bar.high-bar.low
        self.width = movement if self.width is None else self.width+2/(p['width_length']+1)*(movement-self.width)
        slow_length = p['method_value'] if p['entry_method'] == 'slow_trend' else 96
        self.slow = bar.close if self.slow is None else self.slow+2/(slow_length+1)*(bar.close-self.slow)
        self.closes.append(bar.close)
        upper, lower = self.base+p['trigger_mult']*self.width, self.base-p['trigger_mult']*self.width
        long = self.upper is not None and self.pc <= self.upper and bar.close > upper
        short = self.lower is not None and self.pc >= self.lower and bar.close < lower
        self.upper, self.lower, self.pc = upper, lower, bar.close
        self.processed += 1
        if not decisions:
            return None
        action = 'long' if long else 'short' if short else None
        allowed, method_allowed, efficiency = True, True, None
        if action:
            d, method, value = (1 if action == 'long' else -1), p['entry_method'], p['method_value']
            allowed = self.width > 0 and d*(bar.close-self.base) <= 2*self.width
            # Entry filters never suppress the exit caused by a raw opposite signal.
            if method == 'slow_trend':
                method_allowed = d*(bar.close-self.slow) > 0
            elif method == 'efficiency':
                prices = list(self.closes)
                distance = sum(abs(b-a) for a, b in zip(prices, prices[1:]))
                efficiency = abs(prices[-1]-prices[0])/distance if distance else 0.
                method_allowed = len(prices) == 33 and efficiency >= value
            elif method == 'spacing':
                method_allowed = self.last_entry_index is None or index-self.last_entry_index >= value
            elif method == 'alternate':
                method_allowed = action != self.last_entry_side
            if not (allowed and method_allowed):
                action = 'close' if position and position['side'] != action else None
            elif not position or position['side'] != action:
                self.last_entry_index, self.last_entry_side = index, action
        protection = ProfitProtection(p['activation_pct'], p['giveback_pct']) if p['activation_pct'] else None
        intent = Intent(action, reason='反向信号或通道突破', profit_protection=protection) if action else None
        if not p['record_indicators']:
            return intent
        return BarResult(intent, values={'中心线': self.base, '宽度基准': self.width,
                                         '做多门槛': upper, '做空门槛': lower,
                                         '慢趋势参考线': self.slow, '趋势效率': efficiency,
                                         '当前有效保护价': position.get('stop') if position else None},
                         checks={'原做多信号': long, '原做空信号': short, '不追远处突破': allowed,
                                 '入场过滤通过': method_allowed,
                                 '利润保护已启动': bool(position and position.get('protection_active'))},
                         cloud=TrendCloud(self.base+.45*self.width, self.base-.45*self.width, bar.close > self.base))


_calculation = None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed >= len(context.history):
        _calculation = Calculation(context.parameters)
    result = None
    for i in range(_calculation.processed, len(context.history)):
        result = _calculation.update(context.history[i], context.position, decisions=i == len(context.history)-1)
    return result
