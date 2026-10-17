"""Independent EMA55 parameter-study version; execution uses the unchanged project engine."""
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud

STRATEGY = {
    'id': 'trend_cloud_parameters_v4', 'name': 'EMA55 通道参数研究 v4（研究用）',
    'description': '逐项比较中心周期、宽度、突破门槛、追价距离、利润保护和初始止损；默认值复现此前收益第一名。',
    'api_version': '1', 'warmup_bars': 650,
    'parameters': {
        'center_length': {'type': 'int', 'default': 55, 'min': 2, 'max': 200, 'label': '中心线 EMA 周期'},
        'width_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 100, 'label': '高低差 EMA 周期'},
        'trigger_mult': {'type': 'float', 'default': .8, 'min': .1, 'max': 5, 'label': '突破门槛 / 宽度 W'},
        'chase_mult': {'type': 'float', 'default': 2, 'min': 0, 'max': 10, 'label': '离中心最多几倍 W 可入场，0 不限制'},
        'activation_pct': {'type': 'float', 'default': 2, 'min': 0, 'max': 20, 'label': '浮盈多少 % 启动保护，0 关闭'},
        'giveback_pct': {'type': 'float', 'default': 50, 'min': 1, 'max': 99, 'label': '最高浮盈允许回吐 %'},
        'initial_stop_pct': {'type': 'float', 'default': 0, 'min': 0, 'max': 20, 'label': '初始固定止损 %，0 关闭'},
        'initial_stop_width': {'type': 'float', 'default': 0, 'min': 0, 'max': 10, 'label': '初始振幅止损 / W，0 关闭；与固定止损二选一'},
        'record_indicators': {'type': 'bool', 'default': True, 'label': '保存云带和入场条件'},
    },
}


class Calculation:
    def __init__(self, p):
        self.p, self.processed = p, 0
        self.base = self.width = self.pc = self.upper = self.lower = None
        if p['initial_stop_pct'] and p['initial_stop_width']:
            raise ValueError('固定百分比与振幅止损不能同时设置')
        if p['chase_mult'] and p['chase_mult'] <= p['trigger_mult']:
            raise ValueError('允许入场的最远距离必须大于突破门槛')

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
        action = 'long' if long else 'short' if short else None
        allowed = True
        if action:
            d = 1 if action == 'long' else -1
            allowed = self.width > 0 and (p['chase_mult'] == 0 or d*(bar.close-self.base) <= p['chase_mult']*self.width)
            # Distance blocks entry, never an exit on the raw opposite crossing.
            if not allowed:
                action = 'close' if position and position['side'] != action else None
        protection = ProfitProtection(p['activation_pct'], p['giveback_pct']) if p['activation_pct'] else None
        # Width known at the signal close is converted to a percentage. The engine
        # anchors that percentage to the actual next-open fill, and never moves it out.
        stop = (p['initial_stop_pct'] or (100*p['initial_stop_width']*self.width/bar.close)) or None
        intent = Intent(action, reason='反向信号或通道突破', stop_loss_pct=stop,
                        profit_protection=protection) if action else None
        if not p['record_indicators']:
            return intent
        return BarResult(intent, values={'中心线': self.base, '宽度基准': self.width,
                            '做多门槛': upper, '做空门槛': lower,
                            '离中心距离 / W': abs(bar.close-self.base)/self.width if self.width else None,
                            '最远做多价': self.base+p['chase_mult']*self.width if p['chase_mult'] else None,
                            '最远做空价': self.base-p['chase_mult']*self.width if p['chase_mult'] else None,
                            '本次信号初始止损 %': stop,
                            '当前有效保护价': position.get('stop') if position else None},
                         checks={'原做多信号': long, '原做空信号': short, '不追远处突破': allowed,
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
