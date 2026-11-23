"""Remember original EMA55 signals, then use predeclared intrabar stop entries."""
from math import floor, ceil
from collections import deque
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud, StopEntry

STRATEGY = {'id': 'trend_cloud_reverse_after_protection_v5',
 'name': 'EMA通道：浮盈达标后才允许反向退出 v5',
 'description': '原盘中确认规则；可要求利润保护已启动后才接受新的反向退出信号，达标前不反手。',
 'api_version': '1',
 'warmup_bars': 650,
 'parameters': {'center_length': {'type': 'int', 'default': 55, 'min': 2, 'max': 200, 'label': '中心 EMA', 'unit': '根'},
                'width_length': {'type': 'int', 'default': 31, 'min': 2, 'max': 100, 'label': '高低差 EMA', 'unit': '根'},
                'trigger_mult': {'type': 'float',
                                 'default': 0.4,
                                 'min': 0.1,
                                 'max': 5,
                                 'label': '原突破门槛 / W',
                                 'unit': 'W'},
                'chase_mult': {'type': 'float', 'default': 2, 'min': 0, 'max': 10, 'label': '追价上限 / W', 'unit': 'W'},
                'confirmation_level': {'type': 'int',
                                       'default': 1,
                                       'min': 1,
                                       'max': 3,
                                       'label': '突破确认价位',
                                       'options': [{'value': 1, 'label': '信号收盘价'},
                                                   {'value': 2, 'label': '信号最高／最低价'},
                                                   {'value': 3, 'label': '信号实体上／下沿'}]},
                'max_wait_bars': {'type': 'int',
                                  'default': 0,
                                  'min': 0,
                                  'max': 1000,
                                  'label': '信号后最多等待根数',
                                  'unit': '根',
                                  'help': '0 表示不限；2 表示只等待原信号之后两根。'},
                'price_tick': {'type': 'float',
                               'default': 0.01,
                               'min': 1e-06,
                               'max': 100,
                               'label': '突破一个价格单位',
                               'unit': '报价币'},
                'entry_bar_assumption': {'type': 'int',
                                         'default': 0,
                                         'min': 0,
                                         'max': 1,
                                         'label': '入场当根先后顺序',
                                         'options': [{'value': 0, 'label': '入场后止损优先'},
                                                     {'value': 1, 'label': '不利极值视为发生在入场前'}]},
                'activation_pct': {'type': 'float',
                                   'default': 2,
                                   'min': 0,
                                   'max': 20,
                                   'label': '利润保护启动 %',
                                   'unit': '%'},
                'giveback_pct': {'type': 'float',
                                 'default': 50,
                                 'min': 1,
                                 'max': 99,
                                 'label': '最高浮盈回吐 %',
                                 'unit': '%',
                                 'enabled_when': [{'parameter': 'activation_pct', 'value': 0, 'operator': 'gt'}]},
                'initial_stop_pct': {'type': 'float',
                                     'default': 1,
                                     'min': 0,
                                     'max': 20,
                                     'label': '初始止损 %，0 关闭',
                                     'unit': '%',
                                     'enabled_when': [{'parameter': 'stop_method', 'value': 0, 'operator': 'eq'}]},
                'direction_filter': {'type': 'bool', 'default': False, 'label': '仅顺过去6根中心线方向开仓'},
                'stop_method': {'type': 'int',
                                'default': 0,
                                'min': 0,
                                'max': 2,
                                'label': '初始止损方法',
                                'options': [{'value': 0, 'label': '固定百分比'},
                                            {'value': 1, 'label': '高低差 EMA'},
                                            {'value': 2, 'label': 'ATR14'}]},
                'stop_mult': {'type': 'float',
                              'default': 1.5,
                              'min': 0.1,
                              'max': 10,
                              'label': '波动止损倍数',
                              'enabled_when': [{'parameter': 'stop_method', 'value': [1, 2], 'operator': 'in'}]},
                'stop_floor_pct': {'type': 'float',
                                   'default': 0.5,
                                   'min': 0.01,
                                   'max': 10,
                                   'label': '波动止损下限 %',
                                   'unit': '%',
                                   'enabled_when': [{'parameter': 'stop_method', 'value': [1, 2], 'operator': 'in'}]},
                'stop_cap_pct': {'type': 'float',
                                 'default': 2,
                                 'min': 0.01,
                                 'max': 20,
                                 'label': '波动止损上限 %',
                                 'unit': '%',
                                 'enabled_when': [{'parameter': 'stop_method', 'value': [1, 2], 'operator': 'in'}]},
                'reverse_after_protection': {'type': 'bool', 'default': False, 'label': '利润保护启动后才允许反向退出'},
                'stop_reentry': {'type': 'bool', 'default': False, 'label': '止损后突破止损K线极值，最多重进一次'}},
 'rules': ['原盘中确认规则；可要求利润保护已启动后才接受新的反向退出信号，达标前不反手。'],
 'warmup_rule': {'version': '1',
                 'seed_weight_tolerance': 1e-08,
                 'minimum_bars': 1,
                 'terms': [{'kind': 'ema', 'period': 'center_length', 'extra_bars': 7, 'enabled_when': []},
                           {'kind': 'ema', 'period': 'width_length', 'extra_bars': 1, 'enabled_when': []},
                           {'kind': 'rma', 'period': 14, 'extra_bars': 1, 'enabled_when': []}],
                 'explanation': '按当前参数取各指标所需历史的最大值。EMA／RMA 初始值权重降至 1e-8 以下，再覆盖已声明回看窗口；这是数值初始化标准，不保证价格或信号完全相同。'},
 'parameter_constraints': [{'parameter': 'stop_floor_pct',
                            'operator': 'le',
                            'other_parameter': 'stop_cap_pct',
                            'message': '止损下限不能高于上限'}]}


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
        # The engine latches protection_active using completed execution candles.
        # Do not use this signal candle's raw high/low to infer a prior fill.
        reverse_allowed = not p['reverse_after_protection'] or bool(position and position.get('protection_active', False))
        if raw:
            d = 1 if raw=='long' else -1
            if self.waiting and self.waiting['side']!=raw:
                cancelled, self.waiting = True, None
            if position and position['side']!=raw and reverse_allowed:
                intent = Intent('close', reason='原反向信号平仓，盘中突破再入场')
            eligible = self.width>0 and (p['chase_mult']==0 or d*(bar.close-self.base)<=p['chase_mult']*self.width)
            if (position is None or (reverse_allowed and position['side']!=raw)) and self.waiting is None and eligible and aligned(d):
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
            checks={'反向退出已启用':reverse_allowed,'保护前忽略反向':bool(raw and position and position['side']!=raw and not reverse_allowed),
                    '原做多信号':long,'原做空信号':short,'记录新信号':armed,'反向取消旧等待':cancelled,
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
