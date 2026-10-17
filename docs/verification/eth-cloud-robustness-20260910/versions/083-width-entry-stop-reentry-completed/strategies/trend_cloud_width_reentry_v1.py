"""Frozen width/entry/initial-stop/reentry controls based on parameters_v4.

All orders use the project's next-open simulator. No local execution model.
"""
from bisect import bisect_left, insort
from collections import deque
from math import sqrt
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud

STRATEGY = {
    'id': 'trend_cloud_width_reentry_v1', 'name': 'EMA55 宽度与止损后补仓 v1',
    'description': '原版、外线入场、宽窄切换、随宽度止损、止损后补一次；预先固定规则的对照。',
    'api_version': '1', 'warmup_bars': 650,
    'parameters': {
        'center_length': {'type': 'int', 'default': 55, 'min': 2, 'max': 200, 'label': '中心线 EMA'},
        'width_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 100, 'label': '高低差 EMA'},
        'trigger_mult': {'type': 'float', 'default': .4, 'min': .1, 'max': 5, 'label': '原入场门槛 / W'},
        'chase_mult': {'type': 'float', 'default': 2, 'min': 0, 'max': 10, 'label': '原模式追价上限 / W；0 关闭'},
        'outer_mult': {'type': 'float', 'default': 2, 'min': .1, 'max': 10, 'label': '外线 / W'},
        'entry_mode': {'type': 'int', 'default': 0, 'min': 0, 'max': 3, 'label': '0 原版；1 外线；2 通道宽窄切换；3 布林宽窄切换'},
        'dynamic_stop': {'type': 'bool', 'default': False, 'label': '初始止损随通道相对宽度调整'},
        'stop_reentry': {'type': 'bool', 'default': False, 'label': '初始止损后同方向补一次'},
        'reference_bars': {'type': 'int', 'default': 96, 'min': 2, 'max': 500, 'label': '宽度参照根数（15 分钟下约一天）'},
        'narrow_ratio': {'type': 'float', 'default': .8, 'min': .1, 'max': 1, 'label': '进入外线模式的相对宽度'},
        'wide_ratio': {'type': 'float', 'default': 1.2, 'min': 1, 'max': 5, 'label': '返回原模式的相对宽度'},
        'bb_length': {'type': 'int', 'default': 20, 'min': 2, 'max': 100, 'label': '布林周期'},
        'bb_mult': {'type': 'float', 'default': 2, 'min': .1, 'max': 5, 'label': '布林标准差倍数'},
        'activation_pct': {'type': 'float', 'default': 2, 'min': 0, 'max': 20, 'label': '浮盈保护启动 %'},
        'giveback_pct': {'type': 'float', 'default': 50, 'min': 1, 'max': 99, 'label': '最高浮盈回吐 %'},
        'initial_stop_pct': {'type': 'float', 'default': 1, 'min': .1, 'max': 20, 'label': '基础初始止损 %'},
        'min_stop_pct': {'type': 'float', 'default': .5, 'min': .1, 'max': 20, 'label': '随宽度止损下限 %'},
        'max_stop_pct': {'type': 'float', 'default': 2, 'min': .1, 'max': 20, 'label': '随宽度止损上限 %'},
        'record_indicators': {'type': 'bool', 'default': True, 'label': '保存指标与条件'},
    },
}


class PreviousMedian:
    def __init__(self, length):
        self.length, self.queue, self.sorted = length, deque(), []

    def relative_then_append(self, value):
        n = len(self.sorted)
        typical = (self.sorted[n//2] if n % 2 else
                   (self.sorted[n//2-1]+self.sorted[n//2])/2) if n == self.length else None
        ratio = value/typical if typical and typical > 0 else 1.
        self.queue.append(value)
        insort(self.sorted, value)
        if len(self.queue) > self.length:
            self.sorted.pop(bisect_left(self.sorted, self.queue.popleft()))
        return ratio


class Calculation:
    def __init__(self, p):
        self.p, self.processed = p, 0
        self.base = self.width = self.pc = None
        self.narrow = False
        self.channel_reference = PreviousMedian(p['reference_bars'])
        self.bb_reference = PreviousMedian(p['reference_bars'])
        self.closes = deque(maxlen=p['bb_length'])
        self.seen_exit = None
        self.retry_side = None
        self.used = {'long': False, 'short': False}
        self.last_cross_side = None

    def update(self, bar, position=None, decisions=True, last_exit=None):
        p = self.p
        old_base, old_width, old_close = self.base, self.width, self.pc
        # Mode is known before the current candle. A change of multiplier must
        # not itself count as a crossing: compare both candles at SAME multiplier.
        outer = p['entry_mode'] == 1 or (p['entry_mode'] in (2, 3) and self.narrow)
        mult = p['outer_mult'] if outer else p['trigger_mult']
        src = (bar.high+bar.low)/2
        self.base = src if self.base is None else self.base+2/(p['center_length']+1)*(src-self.base)
        movement = bar.high-bar.low
        self.width = movement if self.width is None else self.width+2/(p['width_length']+1)*(movement-self.width)
        upper, lower = self.base+mult*self.width, self.base-mult*self.width
        long = old_close is not None and old_close <= old_base+mult*old_width and bar.close > upper
        short = old_close is not None and old_close >= old_base-mult*old_width and bar.close < lower
        ratio = self.channel_reference.relative_then_append(4*self.width/self.base)
        mode_ratio = ratio
        if p['entry_mode'] == 3:
            self.closes.append(bar.close)
            if len(self.closes) == p['bb_length']:
                mean = sum(self.closes)/len(self.closes)
                sd = sqrt(sum((x-mean)**2 for x in self.closes)/len(self.closes))
                mode_ratio = self.bb_reference.relative_then_append(2*p['bb_mult']*sd/mean)
        if mode_ratio < p['narrow_ratio']:
            self.narrow = True
        elif mode_ratio > p['wide_ratio']:
            self.narrow = False
        self.pc = bar.close
        self.processed += 1
        if not decisions:
            return None

        # Consume a genuine exit once, including entry+stop on the same candle.
        if last_exit and last_exit['trade_id'] != self.seen_exit:
            self.seen_exit = last_exit['trade_id']
            self.retry_side = last_exit['side'] if last_exit['exit_reason'] == 'stop_loss' else None
        raw = 'long' if long else 'short' if short else None
        if raw:
            if self.last_cross_side and raw != self.last_cross_side:
                self.used = {'long': False, 'short': False}
                self.retry_side = None
            self.last_cross_side = raw
            if self.retry_side and raw != self.retry_side:
                self.retry_side = None

        action, reason, retry, allowed = raw, '反向信号或通道突破', False, True
        if action:
            d = 1 if action == 'long' else -1
            allowed = self.width > 0 and (outer or p['chase_mult'] == 0 or
                        d*(bar.close-self.base) <= p['chase_mult']*self.width)
            if not allowed:
                action = 'close' if position and position['side'] != raw else None
        side = self.retry_side
        if p['stop_reentry'] and position is None and side and not self.used[side]:
            d = 1 if side == 'long' else -1
            if d*(bar.close-self.base) > p['outer_mult']*self.width and raw in (None, side):
                action, reason, retry = side, '初始止损后补一次', True
                self.used[side] = True
                self.retry_side = None
        # Reentry variants emit no redundant same-side signal while holding.
        # Other controls preserve the baseline's ignored_same_side records.
        if p['stop_reentry'] and position and action == position['side']:
            action = None
        if action in ('long', 'short') and not retry and (not position or action != position['side']):
            self.retry_side = None
        stop = p['initial_stop_pct']
        if p['dynamic_stop']:
            stop = max(p['min_stop_pct'], min(p['max_stop_pct'], stop*ratio))
        protection = ProfitProtection(p['activation_pct'], p['giveback_pct']) if p['activation_pct'] else None
        intent = Intent(action, reason=reason, stop_loss_pct=stop, profit_protection=protection) if action else None
        if not p['record_indicators']:
            return intent
        return BarResult(intent, values={
            '中心线': self.base, '宽度基准': self.width, '做多门槛': upper, '做空门槛': lower,
            '外侧上沿': self.base+p['outer_mult']*self.width, '外侧下沿': self.base-p['outer_mult']*self.width,
            '通道相对宽度': ratio, '切换参照相对宽度': mode_ratio, '本次初始止损 %': stop,
            '当前有效保护价': position.get('stop') if position else None},
            checks={'外线入场模式': outer, '做多突破': long, '做空突破': short,
                    '距离允许入场': allowed, '本次为补仓': retry,
                    '多向补仓已使用': self.used['long'], '空向补仓已使用': self.used['short']},
            cloud=TrendCloud(self.base+.45*self.width, self.base-.45*self.width, bar.close > self.base))


_calculation = None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed >= len(context.history):
        _calculation = Calculation(context.parameters)
    result = None
    for i in range(_calculation.processed, len(context.history)):
        result = _calculation.update(context.history[i], context.position,
                                    decisions=i == len(context.history)-1, last_exit=context.last_exit)
    return result
