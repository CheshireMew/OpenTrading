"""Controlled cloud-width and execution experiments; no market-data fetching."""
from collections import deque
from app.domain.local_backtest import BarResult, Intent, TrendCloud

STRATEGY = {'id': 'trend_cloud_experiments',
 'name': '趋势通道：ATR 与亏损原因实验',
 'description': '每次只改一个条件。收盘判断，下一开盘成交；入场过滤不阻止原反向信号平仓。实验不代表已确认截图源码。',
 'api_version': '1',
 'warmup_bars': 650,
 'parameters': {'source': {'type': 'str',
                           'default': 'hl2',
                           'label': '中心线价格',
                           'options': [{'value': 'hl2', 'label': '高低均价'}, {'value': 'hlc3', 'label': '高低收均价'}]},
                'width': {'type': 'str',
                          'default': 'range_ema',
                          'label': '宽度来源',
                          'options': [{'value': 'atr', 'label': 'ATR'},
                                      {'value': 'range', 'label': '高低差 RMA'},
                                      {'value': 'range_ema', 'label': '高低差递推平滑'},
                                      {'value': 'fixed', 'label': '固定百分比'},
                                      {'value': 'none', 'label': '零宽度'}]},
                'width_period': {'type': 'int', 'default': 16, 'min': 2, 'max': 50, 'label': 'ATR 或 RMA 宽度周期'},
                'fixed_pct': {'type': 'float',
                              'default': 0.5,
                              'min': 0.001,
                              'max': 10,
                              'label': '固定宽度占中心线 %',
                              'unit': '%',
                              'enabled_when': [{'parameter': 'width', 'value': 'fixed', 'operator': 'eq'}]},
                'entry_filter': {'type': 'str',
                                 'default': 'none',
                                 'label': '入场过滤',
                                 'options': [{'value': 'none', 'label': '无'},
                                             {'value': 'distance2', 'label': '追价距离'},
                                             {'value': 'slope8', 'label': '近8根均线方向'},
                                             {'value': 'efficiency25', 'label': '方向效率至少25%'}]},
                'confirmation': {'type': 'int', 'default': 1, 'min': 1, 'max': 2, 'label': '连续收盘确认根数', 'unit': '根'},
                'stop_atr': {'type': 'float', 'default': 0, 'min': 0, 'max': 10, 'label': '止损距离 / ATR，0 关闭'},
                'target_atr': {'type': 'float', 'default': 0, 'min': 0, 'max': 10, 'label': '止盈距离 / ATR，0 关闭'},
                'trail_atr': {'type': 'float', 'default': 0, 'min': 0, 'max': 10, 'label': '跟随保护距离 / ATR，0 关闭'},
                'record_indicators': {'type': 'bool', 'default': True, 'label': '保存指标和条件'}},
 'rules': ['每次只改一个条件。收盘判断，下一开盘成交；入场过滤不阻止原反向信号平仓。实验不代表已确认截图源码。'],
 'warmup_rule': {'version': '1',
                 'seed_weight_tolerance': 1e-08,
                 'minimum_bars': 1,
                 'terms': [{'kind': 'ema', 'period': 31, 'extra_bars': 9, 'enabled_when': []},
                           {'kind': 'rma', 'period': 'width_period', 'extra_bars': 1, 'enabled_when': []},
                           {'kind': 'rma', 'period': 16, 'extra_bars': 1, 'enabled_when': []},
                           {'kind': 'window', 'period': 21, 'extra_bars': 1, 'enabled_when': []}],
                 'explanation': '按当前参数取各指标所需历史的最大值。EMA／RMA 初始值权重降至 1e-8 以下，再覆盖已声明回看窗口；这是数值初始化标准，不保证价格或信号完全相同。'}}


class Rma:
    def __init__(self, n):
        self.n, self.total, self.count, self.value = n, 0., 0, None

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
        if p['source'] not in ('hl2', 'hlc3') or p['width'] not in ('atr', 'range', 'range_ema', 'fixed', 'none'):
            raise ValueError('Unknown center or width')
        if p['entry_filter'] not in ('none', 'distance2', 'slope8', 'efficiency25'):
            raise ValueError('Unknown entry filter')
        self.p, self.processed = p, 0
        self.atr, self.ranges = Rma(p['width_period']), Rma(p['width_period'])
        self.base = self.range_ema = self.pc = self.pu = self.pl = None
        self.bases, self.closes = deque(maxlen=9), deque(maxlen=21)
        self.awaiting = None

    def update(self, bar, position=None):
        p, pc = self.p, self.pc
        source = (bar.high+bar.low)/2 if p['source'] == 'hl2' else (bar.high+bar.low+bar.close)/3
        self.base = source if self.base is None else self.base+2/32*(source-self.base)
        movement = bar.high-bar.low
        tr = movement if pc is None else max(movement, abs(bar.high-pc), abs(bar.low-pc))
        atr, ranges = self.atr.update(tr), self.ranges.update(movement)
        self.range_ema = movement if self.range_ema is None else self.range_ema+(movement-self.range_ema)/16
        self.bases.append(self.base)
        self.closes.append(bar.close)
        width = {'atr': atr, 'range': ranges, 'range_ema': self.range_ema,
                 'fixed': self.base*p['fixed_pct']/100, 'none': 0.}[p['width']]
        self.processed += 1
        self.pc = bar.close
        if width is None or atr is None:
            return None
        upper, lower = self.base+.99*width, self.base-.99*width
        raw_long = self.pu is not None and pc <= self.pu and bar.close > upper
        raw_short = self.pl is not None and pc >= self.pl and bar.close < lower
        self.pu, self.pl = upper, lower
        raw = 'long' if raw_long else 'short' if raw_short else None
        action = raw
        if p['confirmation'] == 2:
            previous = self.awaiting
            action = previous if ((previous == 'long' and bar.close > upper) or
                                  (previous == 'short' and bar.close < lower)) else None
            self.awaiting = raw if action is None else None
        path = sum(abs(self.closes[i]-self.closes[i-1]) for i in range(1, len(self.closes)))
        efficiency = abs(self.closes[-1]-self.closes[0])/path if path else 0.
        slope = self.bases[-1]-self.bases[0]
        allowed = True
        if action:
            d = 1 if action == 'long' else -1
            if p['entry_filter'] == 'distance2':
                allowed = width > 0 and d*(bar.close-self.base) <= 2*width
            elif p['entry_filter'] == 'slope8':
                allowed = d*slope > 0
            elif p['entry_filter'] == 'efficiency25':
                allowed = efficiency >= .25
            if not allowed:
                # A denied reversal entry must still let the existing side exit.
                action = 'close' if position and position['side'] != action else None
        # Use only signal-close ATR; the engine anchors percentages at the next
        # actual open. This is an ATR-sized percentage, not a future ATR lookup.
        atrpct = 100*atr/bar.close
        intent = Intent(action,
                        stop_loss_pct=p['stop_atr']*atrpct or None,
                        take_profit_pct=p['target_atr']*atrpct or None,
                        trailing_stop_pct=p['trail_atr']*atrpct or None,
                        reason='趋势通道实验') if action else None
        if not p['record_indicators']:
            return intent
        return BarResult(intent, values={'中心线': self.base, '宽度基准': width, 'ATR': atr,
                                         '做多门槛': upper, '做空门槛': lower, '近20根方向一致程度': efficiency},
                         checks={'原做多信号': raw_long, '原做空信号': raw_short, '允许入场': allowed},
                         cloud=TrendCloud(self.base+.45*width, self.base-.45*width, bar.close > self.base))


_calculation = None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed >= len(context.history):
        _calculation = Calculation(context.parameters)
    result = None
    for bar in context.history[_calculation.processed:]:
        result = _calculation.update(bar, context.position)
    return result
