"""Separate study for manual-trading requirements; no change to legacy rules."""
from collections import deque
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud

STRATEGY={
    'id':'trend_cloud_manual_v1','name':'趋势通道：手工交易胜率检查 v1',
    'description':'中心和宽度 EMA31，突破 0.8 倍宽度、超过 2 倍不追。检查突破确认、回踩后入场与不同利润保护；反向信号始终可平仓。',
    'api_version':'1','warmup_bars':650,
    'parameters':{
        'entry_mode':{'type':'str','default':'cross','label':'入场方法：cross / confirm / retest'},
        'confirmation_bars':{'type':'int','default':2,'min':2,'max':8,'label':'连续收在通道外的根数'},
        'retest_bars':{'type':'int','default':8,'min':1,'max':32,'label':'突破后最多等待几根回踩'},
        'efficiency_threshold':{'type':'float','default':.2,'min':0,'max':.9,'label':'过去八小时净移动 / 累计移动的最低比例'},
        'activation_pct':{'type':'float','default':2,'min':0,'max':20,'label':'浮盈多少 % 启动保护，0 关闭'},
        'giveback_pct':{'type':'float','default':50,'min':1,'max':99,'label':'允许最高浮盈回吐 %'},
        'record_indicators':{'type':'bool','default':True,'label':'保存指标和入场条件'},
    },
}


class Calculation:
    def __init__(self,p):
        if p['entry_mode'] not in ('cross','confirm','retest'):
            raise ValueError('Unknown entry mode')
        self.p=p
        self.processed=0
        self.base=self.width=self.pc=self.upper=self.lower=None
        self.closes=deque(maxlen=33)
        self.pending=None

    def update(self,bar,position=None,decisions=True):
        p=self.p
        index=self.processed
        src=(bar.high+bar.low)/2
        self.base=src if self.base is None else self.base+2/32*(src-self.base)
        movement=bar.high-bar.low
        self.width=movement if self.width is None else self.width+2/32*(movement-self.width)
        upper,lower=self.base+.8*self.width,self.base-.8*self.width
        long=self.upper is not None and self.pc<=self.upper and bar.close>upper
        short=self.lower is not None and self.pc>=self.lower and bar.close<lower
        self.pc,self.upper,self.lower=bar.close,upper,lower
        self.closes.append(bar.close)
        prices=list(self.closes)
        path=sum(abs(b-a) for a,b in zip(prices,prices[1:]))
        efficiency=abs(prices[-1]-prices[0])/path if path else 0.
        self.processed+=1
        if not decisions:
            return None
        raw='long' if long else 'short' if short else None
        opposite=bool(raw and position and raw!=position['side'])
        entry=None
        if p['entry_mode']=='cross':
            entry=raw
        else:
            if raw:
                self.pending={'side':raw,'start':index,'consecutive':0}
            if self.pending:
                waiting=self.pending
                direction=1 if waiting['side']=='long' else -1
                threshold=upper if direction==1 else lower
                outside=direction*(bar.close-threshold)>0
                age=index-waiting['start']
                if p['entry_mode']=='confirm':
                    if not outside:
                        self.pending=None
                    else:
                        waiting['consecutive']+=1
                        if waiting['consecutive']>=p['confirmation_bars']:
                            entry=waiting['side']
                            self.pending=None
                else:
                    # Close-confirmed retest: at least one bar after breakout.
                    # A close through the center or an opposite crossing invalidates it.
                    if age>p['retest_bars'] or direction*(bar.close-self.base)<=0:
                        self.pending=None
                    elif age>0 and outside and (bar.low<=threshold if direction==1 else bar.high>=threshold):
                        entry=waiting['side']
                        self.pending=None
        allowed=False
        if entry:
            direction=1 if entry=='long' else -1
            allowed=(self.width>0 and direction*(bar.close-self.base)<=2*self.width and
                     len(prices)==33 and efficiency>=p['efficiency_threshold'])
        # Delaying/filtering new entry never delays a raw opposite exit.
        action=entry if entry and allowed else 'close' if opposite else None
        protection=ProfitProtection(p['activation_pct'],p['giveback_pct']) if p['activation_pct'] else None
        intent=Intent(action,reason='反向信号或通道突破',profit_protection=protection) if action else None
        if not p['record_indicators']:
            return intent
        return BarResult(intent,values={'中心线':self.base,'宽度基准':self.width,'做多门槛':upper,'做空门槛':lower,
                                        '八小时趋势效率':efficiency,'当前有效保护价':position.get('stop') if position else None},
                         checks={'原做多信号':long,'原做空信号':short,'反向退出':opposite,
                                 '入场形态完成':entry is not None,'允许入场':bool(allowed),
                                 '等待确认或回踩':self.pending is not None},
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
