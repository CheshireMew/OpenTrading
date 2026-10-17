"""Frozen ETH screenshot hypotheses, with explicit common execution rules.

Parameters describe candidate formulas, not the unidentified original source.
The simulator handles next-open fills, costs, reversals and final liquidation.
"""
from collections import deque
from app.domain.local_backtest import BarResult, Intent, TrendCloud

STRATEGY = {
    'id': 'trend_cloud_comparison', 'name': '趋势云带长期对照',
    'description': '比较原反转规则、截图穿越候选、高低价通道和均线基准。反向信号换仓，不叠加同向仓位，不把 TP/SL 标签当订单。',
    'api_version': '1', 'warmup_bars': 650,
    'parameters': {
        'variant': {'type': 'str', 'default': 'ema31_atr', 'label': '公式编号（见长期对照报告）'},
        'record_indicators': {'type': 'bool', 'default': True, 'label': '保存每根云带'},
        'long_only': {'type': 'bool', 'default': False, 'label': '仅做多（做空信号改为平仓）'},
    },
}


class Rma:
    def __init__(self, n):
        self.n, self.count, self.total, self.value = n, 0, 0., None

    def update(self, x):
        if self.value is None:
            self.count += 1
            self.total += x
            if self.count == self.n:
                self.value = self.total/self.n
        else:
            self.value += (x-self.value)/self.n
        return self.value


class Calculation:
    def __init__(self, p):
        # Fixed before the two-year performance is inspected. No profit search.
        variants = {
            'original_05': ('EMA', 'close', 34, 14, .5, 0.),
            'original_15': ('EMA', 'close', 34, 14, 1.5, 0.),
            'ema31_atr': ('EMA', 'hlc3', 31, 14, .45, .99),
            'ema31_range': ('EMA', 'hlc3', 31, 14, .45, .99),
            'ema30_hlc3': ('EMA', 'hlc3', 30, 14, .45, .95),
            'ema30_hl2': ('EMA', 'hl2', 30, 14, .45, .95),
            'ema29_close': ('EMA', 'close', 29, 14, .45, .9),
            'high_low_ema': ('EMA', 'hl2', 31, 16, .45, .99),
            'wma41_atr': ('WMA', 'close', 41, 16, .45, .99),
            'sma28_atr': ('SMA', 'close', 28, 16, .45, .99),
            'dual_ema': ('DUAL', 'hl2', 31, 14, 1., 2.2),
            'ema31_cross': ('EMA', 'hlc3', 31, 14, .45, 0.),
            'buy_hold': ('EMA', 'close', 31, 14, .45, 0.),
            'cash': ('EMA', 'close', 31, 14, .45, 0.),
        }
        if p['variant'] not in variants:
            raise ValueError('未知公式编号：'+p['variant'])
        self.p, self.variant = p, p['variant']
        self.kind, self.source, self.n, wn, self.cloud_mult, self.trigger_mult = variants[self.variant]
        self.width, self.gain, self.loss = Rma(wn), Rma(14), Rma(14)
        self.base, self.fast, self.slow, self.range_ema = None, None, None, None
        self.previous_close, self.previous_upper, self.previous_lower = None, None, None
        self.last_signal, self.processed = None, 0
        self.window, self.volumes = deque(maxlen=self.n), deque(maxlen=20)

    def update(self, bar):
        pc = self.previous_close
        source = bar.close if self.source == 'close' else (bar.high+bar.low)/2 if self.source == 'hl2' else (bar.high+bar.low+bar.close)/3
        self.window.append(source)
        if self.kind in ('EMA', 'DUAL'):
            self.base = source if self.base is None else self.base+2/(self.n+1)*(source-self.base)
        elif len(self.window) == self.n:
            self.base = sum(self.window)/self.n if self.kind == 'SMA' else sum((i+1)*v for i, v in enumerate(self.window))/(self.n*(self.n+1)/2)
        if self.kind == 'DUAL':
            self.fast = source if self.fast is None else self.fast+2/27*(source-self.fast)
            self.slow = source if self.slow is None else self.slow+2/37*(source-self.slow)
            self.base = (self.fast+self.slow)/2
        movement = bar.high-bar.low
        tr = movement if pc is None else max(movement, abs(bar.high-pc), abs(bar.low-pc))
        width = self.width.update(movement if self.variant == 'ema31_range' else tr)
        if self.variant == 'high_low_ema':
            self.range_ema = movement if self.range_ema is None else self.range_ema+(movement-self.range_ema)/16
            width = self.range_ema
        elif self.kind == 'DUAL':
            width = abs(self.fast-self.slow)/2
        self.volumes.append(bar.volume)
        if pc is not None:
            self.gain.update(max(bar.close-pc, 0))
            self.loss.update(max(pc-bar.close, 0))
        gain, loss = self.gain.value, self.loss.value
        rsi = None if gain is None else 100. if loss == 0 and gain > 0 else 0. if gain == 0 and loss > 0 else None if loss == 0 else 100-100/(1+gain/loss)
        long = short = False
        cloud, values, checks = None, {}, {}
        if self.base is not None and width is not None:
            upper, lower = self.base+self.cloud_mult*width, self.base-self.cloud_mult*width
            trigger_upper, trigger_lower = self.base+self.trigger_mult*width, self.base-self.trigger_mult*width
            cloud = TrendCloud(upper, lower, bar.close > self.base)
            if self.variant.startswith('original_'):
                inside = lower < bar.close < upper
                volume_spike = len(self.volumes) == 20 and bar.volume > sum(self.volumes)/20*1.8
                cooled = self.last_signal is None or self.processed-self.last_signal > 10
                long = inside and bar.close < self.base and rsi is not None and rsi < 40 and volume_spike and cooled
                short = inside and bar.close > self.base and rsi is not None and rsi > 60 and volume_spike and cooled
            elif self.variant not in ('cash', 'buy_hold'):
                long = self.previous_upper is not None and pc <= self.previous_upper and bar.close > trigger_upper
                short = self.previous_lower is not None and pc >= self.previous_lower and bar.close < trigger_lower
            values = {'中心线': self.base, '宽度基准': width, '做多门槛': trigger_upper, '做空门槛': trigger_lower}
            checks = {'做多信号': long, '做空信号': short}
            self.previous_upper, self.previous_lower = trigger_upper, trigger_lower
        if long or short:
            self.last_signal = self.processed
        self.processed += 1
        self.previous_close = bar.close
        action = 'long' if long else ('close' if self.p['long_only'] else 'short') if short else None
        intent = Intent(action, reason=self.variant) if action else None
        if self.p['record_indicators']:
            return BarResult(intent=intent, cloud=cloud, values=values, checks=checks)
        return intent


_calculation = None
_buy_issued = False


def on_bar(context):
    global _calculation, _buy_issued
    if _calculation is None or _calculation.processed >= len(context.history):
        _calculation = Calculation(context.parameters)
        _buy_issued = False
    result = None
    for bar in context.history[_calculation.processed:]:
        result = _calculation.update(bar)
    if context.parameters['variant'] == 'buy_hold' and not _buy_issued:
        _buy_issued = True
        return Intent('long', reason='首个正式收盘发出一次买入，下一根开盘成交，持有至结束')
    return result
