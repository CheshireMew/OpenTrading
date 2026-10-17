"""High-low cloud with independent reversal and profit-giveback exits."""
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud

STRATEGY = {
    'id': 'trend_cloud_profit_protection', 'name': '趋势通道：利润保护或反向信号退出',
    'description': '中心线 EMA31；宽度和触发倍数可调。突破过远不追单，反向信号平仓；盈利达到启动值后，回吐指定比例也平仓。两种退出条件独立生效。',
    'api_version': '1', 'warmup_bars': 650,
    'parameters': {
        'width_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 100, 'label': '高低差 EMA 周期'},
        'trigger_mult': {'type': 'float', 'default': .99, 'min': .1, 'max': 1.9, 'label': '交易门槛距离 / 宽度'},
        'activation_pct': {'type': 'float', 'default': 0, 'min': 0, 'max': 20, 'label': '盈利达到多少 % 启动保护，0 关闭'},
        'giveback_pct': {'type': 'float', 'default': 40, 'min': 1, 'max': 99, 'label': '允许回吐最高浮盈的 %'},
        'record_indicators': {'type': 'bool', 'default': True, 'label': '保存云带和入场条件'},
    },
}


class Calculation:
    def __init__(self, p):
        self.p, self.processed = p, 0
        self.base = self.width = self.pc = self.upper = self.lower = None

    def update(self, bar, position=None):
        p = self.p
        src = (bar.high+bar.low)/2
        self.base = src if self.base is None else self.base+2/32*(src-self.base)
        movement = bar.high-bar.low
        self.width = movement if self.width is None else self.width+2/(p['width_length']+1)*(movement-self.width)
        upper, lower = self.base+p['trigger_mult']*self.width, self.base-p['trigger_mult']*self.width
        long = self.upper is not None and self.pc <= self.upper and bar.close > upper
        short = self.lower is not None and self.pc >= self.lower and bar.close < lower
        self.upper, self.lower, self.pc = upper, lower, bar.close
        self.processed += 1
        action = 'long' if long else 'short' if short else None
        allowed = True
        if action:
            d = 1 if action == 'long' else -1
            allowed = self.width > 0 and d*(bar.close-self.base) <= 2*self.width
            if not allowed:
                action = 'close' if position and position['side'] != action else None
        protection = ProfitProtection(p['activation_pct'], p['giveback_pct']) if p['activation_pct'] else None
        intent = Intent(action, reason='反向信号或通道突破', profit_protection=protection) if action else None
        if not p['record_indicators']:
            return intent
        return BarResult(intent, values={'中心线': self.base, '宽度基准': self.width,
                                         '做多门槛': upper, '做空门槛': lower,
                                         '当前有效保护价': position.get('stop') if position else None},
                         checks={'原做多信号': long, '原做空信号': short, '允许入场': allowed,
                                 '利润保护已启动': bool(position and position.get('protection_active'))},
                         cloud=TrendCloud(self.base+.45*self.width, self.base-.45*self.width, bar.close > self.base))


_calculation = None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed >= len(context.history):
        _calculation = Calculation(context.parameters)
    result = None
    for bar in context.history[_calculation.processed:]:
        result = _calculation.update(bar, context.position)
    return result
