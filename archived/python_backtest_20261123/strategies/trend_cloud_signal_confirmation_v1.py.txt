"""One remembered original entry signal, confirmed by a later close.

Derived from trend_cloud_parameters_v4; uses the unchanged project simulator.
"""
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud

STRATEGY = {'id': 'trend_cloud_signal_confirmation_v1',
 'name': 'EMA55 原信号积累后确认 v1',
 'description': '记住原入场信号；后续收盘突破信号收盘、影线或实体才入场；反向信号取消旧等待。',
 'api_version': '1',
 'warmup_bars': 650,
 'parameters': {'center_length': {'type': 'int', 'default': 55, 'min': 2, 'max': 200, 'label': '中心线 EMA', 'unit': '根'},
                'width_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 100, 'label': '高低差 EMA', 'unit': '根'},
                'trigger_mult': {'type': 'float',
                                 'default': 0.4,
                                 'min': 0.1,
                                 'max': 5,
                                 'label': '原突破门槛 / W',
                                 'unit': 'W'},
                'chase_mult': {'type': 'float', 'default': 2, 'min': 0, 'max': 10, 'label': '原追价上限 / W', 'unit': 'W'},
                'confirmation_level': {'type': 'int',
                                       'default': 1,
                                       'min': 0,
                                       'max': 3,
                                       'label': '突破确认价位',
                                       'options': [{'value': 0, 'label': '原版收盘信号'},
                                                   {'value': 1, 'label': '信号收盘价'},
                                                   {'value': 2, 'label': '信号最高／最低价'},
                                                   {'value': 3, 'label': '信号实体上／下沿'}]},
                'max_wait_bars': {'type': 'int',
                                  'default': 0,
                                  'min': 0,
                                  'max': 1000,
                                  'label': '信号后最多等待根数',
                                  'unit': '根',
                                  'help': '0 表示不限；2 表示只等待原信号之后两根。',
                                  'enabled_when': [{'parameter': 'confirmation_level', 'value': 0, 'operator': 'gt'}]},
                'activation_pct': {'type': 'float',
                                   'default': 2,
                                   'min': 0,
                                   'max': 20,
                                   'label': '浮盈保护启动 %',
                                   'unit': '%'},
                'giveback_pct': {'type': 'float',
                                 'default': 50,
                                 'min': 1,
                                 'max': 99,
                                 'label': '最高浮盈允许回吐 %',
                                 'unit': '%',
                                 'enabled_when': [{'parameter': 'activation_pct', 'value': 0, 'operator': 'gt'}]},
                'initial_stop_pct': {'type': 'float',
                                     'default': 1,
                                     'min': 0.1,
                                     'max': 20,
                                     'label': '初始止损 %',
                                     'unit': '%'},
                'record_indicators': {'type': 'bool', 'default': True, 'label': '保存原信号、等待及确认条件'}},
 'rules': ['记住原入场信号；后续收盘突破信号收盘、影线或实体才入场；反向信号取消旧等待。'],
 'warmup_rule': {'version': '1',
                 'seed_weight_tolerance': 1e-08,
                 'minimum_bars': 1,
                 'terms': [{'kind': 'ema', 'period': 'center_length', 'extra_bars': 7, 'enabled_when': []},
                           {'kind': 'ema', 'period': 'width_length', 'extra_bars': 1, 'enabled_when': []}],
                 'explanation': '按当前参数取各指标所需历史的最大值。EMA／RMA 初始值权重降至 1e-8 以下，再覆盖已声明回看窗口；这是数值初始化标准，不保证价格或信号完全相同。'}}


class Calculation:
    def __init__(self, p):
        self.p, self.processed = p, 0
        self.base = self.width = self.pc = self.upper = self.lower = None
        self.waiting = None

    def update(self, bar, position=None, decisions=True):
        p = self.p
        src = (bar.high+bar.low)/2
        self.base = src if self.base is None else self.base+2/(p['center_length']+1)*(src-self.base)
        movement = bar.high-bar.low
        self.width = movement if self.width is None else self.width+2/(p['width_length']+1)*(movement-self.width)
        upper, lower = self.base+p['trigger_mult']*self.width, self.base-p['trigger_mult']*self.width
        long = self.upper is not None and self.pc <= self.upper and bar.close > upper
        short = self.lower is not None and self.pc >= self.lower and bar.close < lower
        self.upper, self.lower, self.pc = upper, lower, bar.close
        self.processed += 1
        if not decisions:
            return None
        raw = 'long' if long else 'short' if short else None

        def not_far(side):
            d = 1 if side == 'long' else -1
            return self.width > 0 and (p['chase_mult'] == 0 or d*(bar.close-self.base) <= p['chase_mult']*self.width)

        action, reason = None, '反向信号或通道突破'
        armed = confirmed = cancelled = expired = False
        breakout = on_side = confirmation_near = False
        origin = None
        if p['confirmation_level'] == 0:
            action = raw
            if raw and not not_far(raw):
                action = 'close' if position and position['side'] != raw else None
        else:
            if self.waiting and p['max_wait_bars'] and self.processed-self.waiting['index'] > p['max_wait_bars']:
                expired, self.waiting = True, None
            if raw:
                if self.waiting and self.waiting['side'] != raw:
                    cancelled, self.waiting = True, None
                # Existing exits retain their original timing. New reverse entry
                # must wait for a subsequent candle's confirmation independently.
                if position and position['side'] != raw:
                    action, reason = 'close', '原反向信号先平仓，等待新方向确认'
                can_arm = position is None or position['side'] != raw
                if can_arm and self.waiting is None and not_far(raw):
                    target = bar.close
                    if p['confirmation_level'] == 2:
                        target = bar.high if raw == 'long' else bar.low
                    elif p['confirmation_level'] == 3:
                        target = max(bar.open, bar.close) if raw == 'long' else min(bar.open, bar.close)
                    self.waiting = dict(side=raw, timestamp=bar.timestamp, index=self.processed, target=target)
                    armed = True
            if self.waiting:
                origin = dict(self.waiting)
                side = origin['side']; d = 1 if side == 'long' else -1
                age = self.processed-origin['index']
                breakout = d*(bar.close-origin['target']) > 0
                on_side = bar.close > upper if d == 1 else bar.close < lower
                confirmation_near = not_far(side)
                if age >= 1 and position is None and breakout and on_side and confirmation_near:
                    action, reason = side, '原信号积累后收盘确认'
                    confirmed, self.waiting = True, None
        protection = ProfitProtection(p['activation_pct'], p['giveback_pct']) if p['activation_pct'] else None
        intent = Intent(action, reason=reason, stop_loss_pct=p['initial_stop_pct'], profit_protection=protection) if action else None
        if not p['record_indicators']:
            return intent
        return BarResult(intent, values={
            '中心线': self.base, '宽度基准': self.width, '做多门槛': upper, '做空门槛': lower,
            '外侧上沿': self.base+2*self.width, '外侧下沿': self.base-2*self.width,
            '确认起点时间': origin['timestamp'] if origin else None,
            '待确认方向': (1 if origin['side']=='long' else -1) if origin else 0,
            '确认价格': origin['target'] if origin else None,
            '已等待根数': self.processed-origin['index'] if origin else None,
            '当前有效保护价': position.get('stop') if position else None},
            checks={'原做多信号': long, '原做空信号': short,
                    '记录新信号': armed, '反向取消旧等待': cancelled, '等待过期': expired,
                    '收盘突破确认价格': breakout, '仍在通道对应方向': on_side,
                    '确认时不追远处': confirmation_near, '本次确认入场': confirmed},
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
