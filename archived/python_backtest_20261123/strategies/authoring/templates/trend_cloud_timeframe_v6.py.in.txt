"""Original cloud strategy with timeframe-aware opposite-close confirmation, v6.

All rules and numeric trading parameters preserve v4/v5.
The confirmation interval is inferred only from already-observed warmup bars.
Zero ATR multiplier and one confirmation bar exactly preserve v4. The cloud
still uses EMA(high-low); ATR changes the initial stop only. Stop distance is
frozen at the confirmed signal close and anchored to the next actual fill.
"""
from copy import deepcopy
from dataclasses import replace
from app.domain.local_backtest import BarResult, Intent, ProfitProtection
from strategies.trend_cloud_parameters_v4 import STRATEGY as V4_SPEC, Calculation as V4Calculation

STRATEGY=deepcopy(V4_SPEC)
STRATEGY.update(id='trend_cloud_timeframe_v6',name='原通道策略：多周期适配 v6（研究用）',
                description='独立保留v4；可按ATR设置初始止损，反向信号等待连续收盘确认。')
STRATEGY['parameters'].update({
    'atr_length':dict(type='int',default=14,min=2,max=100,label='ATR的Wilder平均周期'),
    'atr_stop_mult':dict(type='float',default=0,min=0,max=10,label='初始止损ATR倍数，0沿用原止损'),
    'reverse_confirm_bars':dict(type='int',default=1,min=1,max=3,label='反向平仓需要连续几根收盘确认'),
})


class Calculation(V4Calculation):
    def __init__(self,p,step_ms=900000):
        super().__init__(p)
        self.step_ms=step_ms
        self.atr=None;self.tr_sum=0.;self.tr_count=0;self.previous_close=None
        self.pending=None

    def update(self,bar,position=None,decisions=True):
        tr=bar.high-bar.low if self.previous_close is None else max(bar.high-bar.low,abs(bar.high-self.previous_close),abs(bar.low-self.previous_close))
        self.previous_close=bar.close;self.tr_count+=1
        if self.atr is None:
            self.tr_sum+=tr
            if self.tr_count==self.p['atr_length']:self.atr=self.tr_sum/self.p['atr_length']
        else:self.atr+=(tr-self.atr)/self.p['atr_length']
        raw=super().update(bar,position,decisions)
        if not decisions:return raw
        intent=raw.intent if isinstance(raw,BarResult) else raw
        p=self.p;required=p['reverse_confirm_bars']
        raw_side=('long' if bar.close>self.upper else 'short' if bar.close<self.lower else None) if intent else None
        if required>1:
            pending=self.pending
            # A stop/protection exit or a new position cancels the old request.
            if pending and (not position or pending['trade_id']!=position.get('trade_id')):
                self.pending=None;pending=None
            if pending:
                beyond=bar.close>self.upper if pending['side']=='long' else bar.close<self.lower
                if beyond and bar.timestamp-pending['timestamp']==self.step_ms:
                    pending['count']+=1;pending['timestamp']=bar.timestamp
                    if pending['count']>=required:
                        d=1 if pending['side']=='long' else -1
                        allowed=self.width>0 and (p['chase_mult']==0 or d*(bar.close-self.base)<=p['chase_mult']*self.width)
                        stop=(p['initial_stop_pct'] or 100*p['initial_stop_width']*self.width/bar.close) or None
                        protection=ProfitProtection(p['activation_pct'],p['giveback_pct']) if p['activation_pct'] else None
                        intent=Intent(pending['side'] if allowed else 'close',stop_loss_pct=stop,
                                      profit_protection=protection,reason='反向信号连续收盘确认')
                        self.pending=None
                    else:intent=None
                else:
                    self.pending=None;intent=None
            elif position and raw_side and raw_side!=position['side']:
                self.pending=dict(side=raw_side,count=1,timestamp=bar.timestamp,trade_id=position.get('trade_id'))
                intent=None
        if intent and intent.action in ('long','short') and p['atr_stop_mult']:
            if self.atr is None:raise ValueError('ATR尚未完成预热')
            intent=replace(intent,stop_loss_pct=None,stop_loss_distance=self.atr*p['atr_stop_mult'])
        if isinstance(raw,BarResult):
            return replace(raw,intent=intent,values={**raw.values,'ATR':self.atr,
                '反向等待确认根数':self.pending['count'] if self.pending else 0})
        return intent


_calculation=None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed>=len(context.history):
        _calculation=Calculation(context.parameters,step_ms=min(context.history[i].timestamp-context.history[i-1].timestamp for i in range(1,min(len(context.history),650))))
    result=None
    for i in range(_calculation.processed,len(context.history)):
        result=_calculation.update(context.history[i],context.position,decisions=i==len(context.history)-1)
    return result
