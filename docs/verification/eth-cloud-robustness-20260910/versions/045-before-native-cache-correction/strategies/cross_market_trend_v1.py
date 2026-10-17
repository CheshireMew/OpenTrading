"""Three causal trend baselines; native 4h/daily closes, fixed entry ATR stop."""
from collections import deque
from app.domain.local_backtest import Intent, BarResult

STRATEGY = {
    'id': 'cross_market_trend_v1', 'name': '跨标的趋势基准 v1：突破、双均线、涨跌方向',
    'description': '按所选K线周期入场与退出；ATR14初始止损固定，不叠加百分比利润保护。',
    'api_version': '1', 'warmup_bars': 200,
    'parameters': {
        'family': {'type':'str','default':'breakout','label':'breakout / average / momentum'},
        'entry_length': {'type':'int','default':20,'min':2,'max':150,'label':'突破或涨跌回看根数'},
        'exit_length': {'type':'int','default':10,'min':2,'max':100,'label':'突破策略退出回看根数'},
        'fast_length': {'type':'int','default':20,'min':2,'max':100,'label':'较快简单均线周期'},
        'slow_length': {'type':'int','default':60,'min':3,'max':150,'label':'较慢简单均线周期'},
        'atr_length': {'type':'int','default':14,'min':2,'max':50,'label':'Wilder ATR周期'},
        'atr_mult': {'type':'float','default':3.,'min':.1,'max':10,'label':'初始止损距离 / ATR'},
        'record_indicators': {'type':'bool','default':True,'label':'保存指标和入场条件'},
    }
}


class Calculation:
    def __init__(self,p):
        if p['family'] not in ('breakout','average','momentum'):raise ValueError('未知趋势规则')
        if p['fast_length']>=p['slow_length']:raise ValueError('快均线周期必须小于慢均线周期')
        if p['exit_length']>=p['entry_length'] and p['family']=='breakout':raise ValueError('退出周期必须短于突破周期')
        self.p=p;self.processed=0;self.bars=deque(maxlen=151);self.atr=None;self.tr_sum=0.
        self.previous_close=None;self.previous_direction=0;self.started=False

    def update(self,b,position=None,decisions=True):
        p=self.p;past=list(self.bars);family=p['family'];intent=None
        tr=b.high-b.low if self.previous_close is None else max(b.high-b.low,abs(b.high-self.previous_close),abs(b.low-self.previous_close))
        self.previous_close=b.close;self.processed+=1
        if self.atr is None:
            self.tr_sum+=tr
            if self.processed==p['atr_length']:self.atr=self.tr_sum/p['atr_length']
        else:self.atr+=(tr-self.atr)/p['atr_length']
        values={'ATR':self.atr};direction=0;action=None
        if family=='breakout' and len(past)>=p['entry_length']:
            upper=max(x.high for x in past[-p['entry_length']:]);lower=min(x.low for x in past[-p['entry_length']:])
            exit_upper=max(x.high for x in past[-p['exit_length']:]);exit_lower=min(x.low for x in past[-p['exit_length']:])
            values.update(做多突破价=upper,做空突破价=lower,多单退出价=exit_lower,空单退出价=exit_upper)
            if b.close>upper:action='long'
            elif b.close<lower:action='short'
            elif position and ((position['side']=='long' and b.close<exit_lower) or (position['side']=='short' and b.close>exit_upper)):action='close'
        elif family in ('average','momentum'):
            if family=='average' and len(past)+1>=p['slow_length']:
                closes=[x.close for x in past]+[b.close]
                fast=sum(closes[-p['fast_length']:])/p['fast_length'];slow=sum(closes[-p['slow_length']:])/p['slow_length']
                values.update(快均线=fast,慢均线=slow)
                direction=1 if fast>slow else -1 if fast<slow else 0
            elif family=='momentum' and len(past)>=p['entry_length']:
                reference=past[-p['entry_length']].close
                change=b.close/reference-1;direction=1 if change>0 else -1 if change<0 else 0
                values.update(比较起点价格=reference,过去涨跌百分比=100*change)
            # Enter the known regime once at study start, then only on a change.
            # An initial stop does not immediately reopen the same trend daily.
            if direction and (not self.started or direction!=self.previous_direction):action='long' if direction>0 else 'short'
            elif direction==0 and self.previous_direction and position:action='close'
            self.previous_direction=direction
        self.bars.append(b)
        if not decisions:return None
        self.started=True
        if action in ('long','short'):
            if self.atr is None:raise ValueError('ATR尚未完成预热')
            distance=p['atr_mult']*self.atr
            # No valid positive-price long stop can be set at this known close.
            if action=='long' and distance>=b.close:
                action='close' if position and position['side']=='short' else None
            if action in ('long','short'):
                intent=Intent(action,stop_loss_distance=distance,reason=family+' 趋势触发')
        if action=='close':intent=Intent('close',reason=family+' 趋势退出')
        return BarResult(intent,values=values) if p['record_indicators'] else intent


_calculation=None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed>=len(context.history):_calculation=Calculation(context.parameters)
    result=None
    for i in range(_calculation.processed,len(context.history)):
        result=_calculation.update(context.history[i],context.position,decisions=i==len(context.history)-1)
    return result
