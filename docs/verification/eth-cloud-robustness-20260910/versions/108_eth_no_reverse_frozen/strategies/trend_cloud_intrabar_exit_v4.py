"""Remember original EMA55 signals, then use predeclared intrabar stop entries."""
from math import floor, ceil
from collections import deque
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud, StopEntry

STRATEGY = {
    'id': 'trend_cloud_intrabar_exit_v4', 'name': 'EMA通道盘中确认：反向退出开关 v4',
    'description': '原信号收盘后记录价位，从下一根开始盘中突破即入场；反向重置，一次消费。',
    'api_version': '1', 'warmup_bars': 650,
    'parameters': {
        'center_length': {'type': 'int', 'default': 55, 'min': 2, 'max': 200, 'label': '中心 EMA'},
        'width_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 100, 'label': '高低差 EMA'},
        'trigger_mult': {'type': 'float', 'default': .4, 'min': .1, 'max': 5, 'label': '原突破门槛 / W'},
        'chase_mult': {'type': 'float', 'default': 2, 'min': 0, 'max': 10, 'label': '追价上限 / W'},
        'confirmation_level': {'type': 'int', 'default': 1, 'min': 1, 'max': 3, 'label': '1 信号收盘；2 最高最低；3 实体'},
        'max_wait_bars': {'type': 'int', 'default': 0, 'min': 0, 'max': 1000, 'label': '0 不限；2 仅信号后两根'},
        'price_tick': {'type': 'float', 'default': .01, 'min': .000001, 'max': 100, 'label': '突破一个价格单位'},
        'entry_bar_assumption': {'type': 'int', 'default': 0, 'min': 0, 'max': 1, 'label': '先后不明：0 算入场后止损；1 算不利极值发生在入场前'},
        'activation_pct': {'type': 'float', 'default': 2, 'min': 0, 'max': 20, 'label': '利润保护启动 %'},
        'giveback_pct': {'type': 'float', 'default': 50, 'min': 1, 'max': 99, 'label': '最高浮盈回吐 %'},
        'initial_stop_pct': {'type': 'float', 'default': 1, 'min': 0, 'max': 20, 'label': '初始止损 %，0 关闭'},
        'direction_filter': {'type': 'bool', 'default': False, 'label': '仅顺过去6根中心线方向开仓'},
        'stop_method': {'type': 'int', 'default': 0, 'min': 0, 'max': 2, 'label': '0固定；1振幅EMA；2 ATR14'},
        'stop_mult': {'type': 'float', 'default': 1.5, 'min': .1, 'max': 10, 'label': '波动止损倍数'},
        'stop_floor_pct': {'type': 'float', 'default': .5, 'min': .01, 'max': 10, 'label': '波动止损下限 %'},
        'stop_cap_pct': {'type': 'float', 'default': 2, 'min': .01, 'max': 20, 'label': '波动止损上限 %'},
        'reverse_exit': {'type': 'bool', 'default': True, 'label': '反向信号平仓；关闭后持仓中不反手'},
        'stop_reentry': {'type': 'bool', 'default': False, 'label': '止损后突破止损K线极值，最多重进一次'},
    },
}


class Calculation:
    def __init__(self, p):
        self.p, self.processed = p, 0
        self.base = self.width = self.pc = self.upper = self.lower = None
        self.waiting = None
        self.centers = deque(maxlen=7)
        self.atr = None
        self.tr_seed = []
        self.active = None
        self.handled_exit = None
        if p['stop_floor_pct'] > p['stop_cap_pct']:
            raise ValueError('止损下限不能高于上限')

    def update(self, bar, position=None, last_exit=None, decisions=True):
        p = self.p
        src, movement = (bar.high+bar.low)/2, bar.high-bar.low
        tr = movement if self.pc is None else max(movement,abs(bar.high-self.pc),abs(bar.low-self.pc))
        if self.atr is None:
            self.tr_seed.append(tr)
            if len(self.tr_seed)==14: self.atr=sum(self.tr_seed)/14
        else:
            self.atr += (tr-self.atr)/14
        self.base = src if self.base is None else self.base+2/(p['center_length']+1)*(src-self.base)
        self.width = movement if self.width is None else self.width+2/(p['width_length']+1)*(movement-self.width)
        upper, lower = self.base+p['trigger_mult']*self.width, self.base-p['trigger_mult']*self.width
        long = self.upper is not None and self.pc <= self.upper and bar.close > upper
        short = self.lower is not None and self.pc >= self.lower and bar.close < lower
        self.upper, self.lower, self.pc = upper, lower, bar.close
        self.processed += 1
        self.centers.append(self.base)
        if not decisions:
            return None
        raw = 'long' if long else 'short' if short else None
        slope = self.centers[-1]-self.centers[0] if len(self.centers)==7 else None
        aligned = lambda d: not p['direction_filter'] or (slope is not None and d*slope>0)
        consumed = cancelled = expired = armed = False
        # Even an entry immediately stopped on this bar consumes its signal.
        if self.waiting:
            w = self.waiting
            filled = any(t is not None and t['side']==w['side'] and t['entry_time']>w['timestamp']
                         for t in (position, last_exit))
            if filled:
                trade=next(t for t in (position,last_exit) if t is not None and t['side']==w['side'] and t['entry_time']>w['timestamp'])
                self.active=dict(side=w['side'],entry_time=trade['entry_time'],origin=w.get('origin',w['timestamp']),retry=w.get('retry',False))
                consumed, self.waiting = True, None
        if self.waiting and not self.waiting.get('retry') and p['max_wait_bars'] and self.processed-self.waiting['index'] >= p['max_wait_bars']:
            expired, self.waiting = True, None
        retry_armed=False
        if self.active and last_exit and (last_exit['entry_time'],last_exit['side'])==(self.active['entry_time'],self.active['side']):
            exit_key=(last_exit['entry_time'],last_exit['exit_time'],last_exit['side'])
            a=self.active
            if exit_key!=self.handled_exit and p['stop_reentry'] and last_exit['exit_reason']=='stop_loss' and not a['retry'] and (raw is None or raw==a['side']):
                self.waiting=dict(side=a['side'],timestamp=bar.timestamp,index=self.processed,
                    target=bar.high if a['side']=='long' else bar.low,origin=a['origin'],retry=True)
                retry_armed=True
            self.handled_exit=exit_key
            self.active=None
        intent = order = None
        if raw:
            d = 1 if raw=='long' else -1
            if self.waiting and self.waiting['side']!=raw:
                cancelled, self.waiting = True, None
            if position and position['side']!=raw and p['reverse_exit']:
                intent = Intent('close', reason='原反向信号平仓，盘中突破再入场')
            eligible = self.width>0 and (p['chase_mult']==0 or d*(bar.close-self.base)<=p['chase_mult']*self.width)
            if (position is None or (p['reverse_exit'] and position['side']!=raw)) and self.waiting is None and eligible and aligned(d):
                target = bar.close
                if p['confirmation_level']==2:
                    target = bar.high if d==1 else bar.low
                elif p['confirmation_level']==3:
                    target = max(bar.open,bar.close) if d==1 else min(bar.open,bar.close)
                self.waiting = dict(side=raw, timestamp=bar.timestamp, index=self.processed, target=target)
                armed = True
        trigger = worst = None
        if self.waiting:
            w = self.waiting; d = 1 if w['side']=='long' else -1
            # Every price is known at this close. The next bar cannot contribute
            # its high/low/close to its own entry level or chase cap.
            threshold = max(w['target'],upper) if d==1 else min(w['target'],lower)
            tick = p['price_tick']
            trigger = round((floor(threshold/tick+1e-8)+1)*tick, 10) if d==1 else round((ceil(threshold/tick-1e-8)-1)*tick, 10)
            worst = self.base+d*p['chase_mult']*self.width if p['chase_mult'] else None
            if trigger>0 and (worst is None or d*(worst-trigger)>=0) and aligned(d):
                protection = ProfitProtection(p['activation_pct'],p['giveback_pct']) if p['activation_pct'] else None
                stop=p['initial_stop_pct'] or None
                if p['stop_method']:
                    scale=self.width if p['stop_method']==1 else self.atr
                    stop=min(p['stop_cap_pct'],max(p['stop_floor_pct'],100*p['stop_mult']*scale/bar.close))
                risk = Intent(w['side'], stop_loss_pct=stop, profit_protection=protection,
                              reason='止损后极值突破重进一次' if w.get('retry') else '原信号积累后盘中突破')
                order = StopEntry(risk,trigger,worst,'stop_first' if p['entry_bar_assumption']==0 else 'adverse_extreme_before_entry')
        w = self.waiting
        return BarResult(intent, values={
            '中心线':self.base,'宽度基准':self.width,'做多门槛':upper,'做空门槛':lower,
            '外侧上沿':self.base+2*self.width,'外侧下沿':self.base-2*self.width,
            '确认起点时间':w['timestamp'] if w else None,'待确认方向':(1 if w['side']=='long' else -1) if w else 0,
            '信号原始价位':w['target'] if w else None,'下根突破入场价':trigger,'下根追价上限':worst,
            '已等待根数':self.processed-w['index'] if w else None,
            '中心线过去6根变化':slope,'ATR14':self.atr,'重进委托':int(bool(w and w.get('retry'))),
            '最初信号时间':w.get('origin',w['timestamp']) if w else None,
            '当前有效保护价':position.get('stop') if position else None},
            checks={'原做多信号':long,'原做空信号':short,'记录新信号':armed,'反向取消旧等待':cancelled,
                    '等待过期':expired,'成交后消费信号':consumed,'挂出下一根突破委托':order is not None,'止损后准备重进':retry_armed},
            cloud=TrendCloud(self.base+.45*self.width,self.base-.45*self.width,bar.close>self.base),entry_order=order)


_calculation = None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed>=len(context.history):
        _calculation = Calculation(context.parameters)
    result = None
    for i in range(_calculation.processed,len(context.history)):
        result = _calculation.update(context.history[i],context.position,context.last_exit,decisions=i==len(context.history)-1)
    return result
