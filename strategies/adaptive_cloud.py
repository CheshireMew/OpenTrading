"""Pine-equivalent original and explicitly fitted crossing hypothesis.

Original formula supplied by the user, credited to @darshakssc:
https://www.tradingview.com/script/VRrsRgoB-Adaptive-Trend-Cloud-Smart-Reversal-Zones-darshakssc/
The crossing mode is a reconstruction hypothesis, not the author's source.
It never reads timestamps to decide signals and never accesses future bars.
"""
from collections import deque
from app.domain.local_backtest import BarResult, Intent, TrendCloud

STRATEGY = {'id': 'adaptive_cloud',
 'name': '趋势云带核验',
 'description': 'original 按用户提供的 Pine 规则计算；cross 为截图拟合的穿越候选。保留每根指标和条件，不自动把 TP/SL 标签当成交易订单。',
 'api_version': '1',
 'warmup_bars': 650,
 'parameters': {'mode': {'type': 'str',
                         'default': 'original',
                         'label': '信号规则',
                         'options': [{'value': 'original', 'label': '原 Pine 反转规则'},
                                     {'value': 'cross', 'label': '截图拟合穿越候选'}]},
                'source': {'type': 'str',
                           'default': 'close',
                           'label': '均线价格',
                           'options': [{'value': 'close', 'label': '收盘价'},
                                       {'value': 'hlc3', 'label': '高低收均价'},
                                       {'value': 'hl2', 'label': '高低均价'}]},
                'ema_length': {'type': 'int', 'default': 34, 'min': 2, 'max': 100, 'label': 'EMA 长度', 'unit': '根'},
                'atr_length': {'type': 'int', 'default': 14, 'min': 2, 'max': 50, 'label': 'ATR 长度', 'unit': '根'},
                'cloud_mult': {'type': 'float', 'default': 0.5, 'min': 0.01, 'max': 5, 'label': '可见云带 ATR 系数'},
                'trigger_mult': {'type': 'float',
                                 'default': 0.99,
                                 'min': 0,
                                 'max': 5,
                                 'label': 'cross 信号门槛 ATR 系数',
                                 'unit': 'W',
                                 'enabled_when': [{'parameter': 'mode', 'value': 'cross', 'operator': 'eq'}]},
                'rsi_length': {'type': 'int', 'default': 14, 'min': 2, 'max': 50, 'label': 'RSI 长度', 'unit': '根'},
                'volume_mult': {'type': 'float',
                                'default': 1.8,
                                'min': 0,
                                'max': 20,
                                'label': 'original 成交量倍数',
                                'enabled_when': [{'parameter': 'mode', 'value': 'original', 'operator': 'eq'}]},
                'cooldown': {'type': 'int',
                             'default': 10,
                             'min': 0,
                             'max': 100,
                             'label': 'original 冷却根数（须严格大于）',
                             'unit': '根',
                             'enabled_when': [{'parameter': 'mode', 'value': 'original', 'operator': 'eq'}]}},
 'rules': ['original 按用户提供的 Pine 规则计算；cross 为截图拟合的穿越候选。保留每根指标和条件，不自动把 TP/SL 标签当成交易订单。'],
 'warmup_rule': {'version': '1',
                 'seed_weight_tolerance': 1e-08,
                 'minimum_bars': 1,
                 'terms': [{'kind': 'ema', 'period': 'ema_length', 'extra_bars': 1, 'enabled_when': []},
                           {'kind': 'rma', 'period': 'atr_length', 'extra_bars': 1, 'enabled_when': []},
                           {'kind': 'rma', 'period': 'rsi_length', 'extra_bars': 2, 'enabled_when': []},
                           {'kind': 'window', 'period': 20, 'extra_bars': 1, 'enabled_when': []}],
                 'explanation': '按当前参数取各指标所需历史的最大值。EMA／RMA 初始值权重降至 1e-8 以下，再覆盖已声明回看窗口；这是数值初始化标准，不保证价格或信号完全相同。'},
 'parameter_constraints': [{'parameter': 'source',
                            'operator': 'eq',
                            'value': 'close',
                            'enabled_when': [{'parameter': 'mode', 'value': 'original'}],
                            'message': '原 Pine 规则的均线价格必须为收盘价'}]}


class Rma:
    def __init__(self, length):
        self.length, self.count, self.total, self.value = length, 0, 0., None

    def update(self, value):
        if self.value is None:
            self.count += 1
            self.total += value
            if self.count == self.length:
                self.value = self.total / self.length
        else:
            self.value += (value - self.value) / self.length
        return self.value


class Calculation:
    def __init__(self, p):
        if p['mode'] not in ('original', 'cross') or p['source'] not in ('close', 'hlc3', 'hl2'):
            raise ValueError('mode 应为 original/cross，source 应为 close/hlc3/hl2')
        if p['mode'] == 'original' and p['source'] != 'close':
            raise ValueError('原 Pine 的 src 固定为 close；original 模式须使用 close')
        self.p, self.processed = p, 0
        self.base, self.previous_close, self.previous_upper, self.previous_lower = None, None, None, None
        self.atr, self.gain, self.loss = Rma(p['atr_length']), Rma(p['rsi_length']), Rma(p['rsi_length'])
        self.volumes = deque(maxlen=20)
        self.last_signal = None

    def update(self, b):
        p = self.p
        src = b.close if p['source'] == 'close' else (b.high+b.low+b.close)/3 if p['source'] == 'hlc3' else (b.high+b.low)/2
        self.base = src if self.base is None else self.base+2/(p['ema_length']+1)*(src-self.base)
        pc = self.previous_close
        tr = b.high-b.low if pc is None else max(b.high-b.low, abs(b.high-pc), abs(b.low-pc))
        atr = self.atr.update(tr)
        if pc is not None:
            self.gain.update(max(b.close-pc,0))
            self.loss.update(max(pc-b.close,0))
        gain, loss = self.gain.value, self.loss.value
        rsi = None if gain is None else 100. if loss == 0 and gain > 0 else 0. if gain == 0 and loss > 0 else None if loss == 0 else 100-100/(1+gain/loss)
        self.volumes.append(b.volume)
        mean_volume = sum(self.volumes)/20 if len(self.volumes) == 20 else None
        volume_ratio = b.volume/mean_volume if mean_volume else None
        long = short = False
        upper = lower = trigger_upper = trigger_lower = None
        checks = {}
        cloud = None
        if atr is not None:
            upper, lower = self.base+p['cloud_mult']*atr, self.base-p['cloud_mult']*atr
            trigger_upper, trigger_lower = self.base+p['trigger_mult']*atr, self.base-p['trigger_mult']*atr
            cloud = TrendCloud(upper, lower, b.close > self.base)
            if p['mode'] == 'original':
                inside = lower < b.close < upper
                spike = mean_volume is not None and b.volume > mean_volume*p['volume_mult']
                cooled = self.last_signal is None or self.processed-self.last_signal > p['cooldown']
                checks = {'收盘在云带内': inside, '收盘低于EMA': b.close < self.base,
                    '收盘高于EMA': b.close > self.base, 'RSI小于40': rsi is not None and rsi < 40,
                    'RSI大于60': rsi is not None and rsi > 60, '成交量达标': spike, '冷却完成': cooled}
                long = inside and b.close < self.base and rsi is not None and rsi < 40 and spike and cooled
                short = inside and b.close > self.base and rsi is not None and rsi > 60 and spike and cooled
            else:
                long = self.previous_upper is not None and pc <= self.previous_upper and b.close > trigger_upper
                short = self.previous_lower is not None and pc >= self.previous_lower and b.close < trigger_lower
                checks = {'收盘上穿做多门槛': long, '收盘下穿做空门槛': short}
        self.previous_close, self.previous_upper, self.previous_lower = b.close, trigger_upper, trigger_lower
        if long or short:
            self.last_signal = self.processed
        self.processed += 1
        intent = Intent('long' if long else 'short', reason='原脚本反转条件' if p['mode'] == 'original' else '收盘穿越 EMA ± ATR 门槛（拟合候选）') if long or short else None
        return BarResult(intent=intent, cloud=cloud,
            values={'收盘价':b.close, 'EMA':self.base, 'ATR':atr, 'RSI':rsi, '成交量倍数':volume_ratio,
                    '云带上沿':upper, '云带下沿':lower, '做多门槛':trigger_upper if p['mode']=='cross' else upper,
                    '做空门槛':trigger_lower if p['mode']=='cross' else lower}, checks=checks)


_calculation = None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed >= len(context.history):
        _calculation = Calculation(context.parameters)
    result = None
    for b in context.history[_calculation.processed:]:
        result = _calculation.update(b)
    return result
