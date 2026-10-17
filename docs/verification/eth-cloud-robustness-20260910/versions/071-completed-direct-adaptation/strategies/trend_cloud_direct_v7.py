"""Original cloud framework with price-derived adaptation; no return ranking.

This research strategy requires cloud_adaptive_research_v1.simulate. All false
exactly reproduces v4 intents. Adaptive EMA is NOT standard squared-SC KAMA.
"""
from collections import deque
from copy import deepcopy
from app.domain.local_backtest import Intent, ProfitProtection, TrendCloud
from app.domain.cloud_adaptive_types_v1 import AdaptiveIntent, AdaptiveResult
from strategies.trend_cloud_parameters_v4 import STRATEGY as OLD

STRATEGY = deepcopy(OLD)
STRATEGY.update(id='trend_cloud_direct_v7', name='原通道：直接自适应研究 v7')
STRATEGY['parameters'].update({
    'adaptive_center':dict(type='bool',default=False,label='根据价格方向效率计算均线速度'),
    'scaled_risk':dict(type='bool',default=False,label='2ATR初始止损和4ATR保护启动'),
    'atr_trailing':dict(type='bool',default=False,label='启动后从峰值回撤2ATR退出'),
    'efficiency_gate':dict(type='bool',default=False,label='入场要求31根方向效率至少0.2'),
})


class Calculation:
    def __init__(self,p):
        self.p=p; self.processed=0
        self.base=self.width=self.pc=self.upper=self.lower=None
        self.atr=None; self.trs=[]; self.prices=deque(maxlen=32)
        self.changes=deque(maxlen=31); self.path=0.; self.er=0.
        self.alpha=2/56
        self.audit=[]

    def update(self,bar,position=None,decisions=True):
        p=self.p
        tr=bar.high-bar.low if self.pc is None else max(bar.high-bar.low,abs(bar.high-self.pc),abs(bar.low-self.pc))
        if self.atr is None:
            self.trs.append(tr)
            if len(self.trs)==14:self.atr=sum(self.trs)/14
        else:self.atr+=(tr-self.atr)/14
        if self.pc is not None:
            if len(self.changes)==31:self.path-=self.changes[0]
            change=abs(bar.close-self.pc); self.changes.append(change); self.path+=change
        self.prices.append(bar.close)
        self.er=min(1.,max(0.,abs(bar.close-self.prices[0])/self.path)) if len(self.prices)==32 and self.path>1e-12 else 0.
        # Linear interpolation of EMA smoothing weights, bounded by EMA21/89.
        # These endpoints and ER31 are frozen for all assets before outcomes.
        self.alpha=2/90+self.er*(2/22-2/90) if p['adaptive_center'] else 2/(p['center_length']+1)
        src=(bar.high+bar.low)/2
        self.base=src if self.base is None else self.base+self.alpha*(src-self.base)
        self.width=bar.high-bar.low if self.width is None else self.width+2/(p['width_length']+1)*(bar.high-bar.low-self.width)
        upper,lower=self.base+p['trigger_mult']*self.width,self.base-p['trigger_mult']*self.width
        long=self.upper is not None and self.pc<=self.upper and bar.close>upper
        short=self.lower is not None and self.pc>=self.lower and bar.close<lower
        self.upper,self.lower,self.pc=upper,lower,bar.close; self.processed+=1
        if not decisions:return None
        side='long' if long else 'short' if short else None
        distance=abs(bar.close-self.base)/self.width if self.width else 0.
        near=self.width>0 and (p['chase_mult']==0 or distance<=p['chase_mult'])
        efficient=not p['efficiency_gate'] or self.er>=.2
        action=side
        if side and not (near and efficient):
            action='close' if position and position['side']!=side else None
        stop=(p['initial_stop_pct'] or 100*p['initial_stop_width']*self.width/bar.close) or None
        protection=ProfitProtection(p['activation_pct'],p['giveback_pct']) if p['activation_pct'] else None
        intent=Intent(action,reason='反向信号或通道突破',stop_loss_pct=stop,profit_protection=protection) if action else None
        if intent and action in ('long','short') and p['scaled_risk']:
            if self.atr is None or self.atr<=0:raise ValueError('有效ATR尚未就绪')
            intent=AdaptiveIntent(action,reason='波动尺度止损与启动',stop_loss_distance=2*self.atr,
                profit_protection=ProfitProtection(p['activation_pct'],p['giveback_pct']),activation_distance=4*self.atr)
        if side:
            self.audit.append(dict(timestamp=bar.timestamp,side=side,action=action,near=near,efficient=efficient,
                er=self.er,atr=self.atr,atr_pct=100*self.atr/bar.close,base=self.base,width=self.width,
                distance=distance,equivalent_ema=2/self.alpha-1))
        return AdaptiveResult(intent=intent,trailing_distance=2*self.atr if p['atr_trailing'] else None,
            record_observation=p['record_indicators'],
            values={'中心线':self.base,'宽度基准':self.width,'做多门槛':upper,'做空门槛':lower,
                    'ATR14':self.atr,'方向效率31':self.er,'等效EMA周期':2/self.alpha-1,
                    '当前有效保护价':position.get('stop') if position else None},
            checks={'原做多信号':long,'原做空信号':short,'允许入场':near and efficient},
            cloud=TrendCloud(self.base+.45*self.width,self.base-.45*self.width,bar.close>self.base))


_calculation=None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed>=len(context.history):
        _calculation=Calculation(context.parameters)
    result=None
    for i in range(_calculation.processed,len(context.history)):
        result=_calculation.update(context.history[i],context.position,decisions=i==len(context.history)-1)
    return result
