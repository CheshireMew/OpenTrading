"""Entry-only research. Original ER20 exits and execution are fixed."""
from collections import deque
from app.domain.local_backtest import BarResult, Intent, ProfitProtection, TrendCloud

STRATEGY={
    'id':'trend_cloud_entry_v2','name':'趋势通道：只检查入场 v2',
    'description':'固定 EMA31、宽度门槛 0.8、八小时震荡过滤 20%；保持浮盈 2% 回吐 50% 或反向信号退出，只比较入场条件。',
    'api_version':'1','warmup_bars':650,
    'parameters':{
        'entry_filter':{'type':'str','default':'baseline','label':'附加入场条件（预先固定的研究版本）'},
        'record_indicators':{'type':'bool','default':True,'label':'保存进场前可见的条件'},
    },
}


class Calculation:
    def __init__(self,p):
        self.p=p
        self.processed=0
        self.base=self.width=self.pc=self.upper=self.lower=None
        self.center_side=0
        self.closes=deque(maxlen=33)
        self.bases=deque(maxlen=9)
        self.crossings=deque(maxlen=16)
        self.previous_bars=deque(maxlen=8)
        self.values={}
        if p['entry_filter'] not in ('baseline','aligned_slope','local_trend','few_crossings','strong_close','closer_entry','no_spike','active_market','structure_break'):
            raise ValueError('Unknown frozen entry filter')

    def features(self,d):
        v=self.values
        return dict(slope_2h=d*v['slope_2h'],efficiency_2h=v['efficiency_2h'],
                    center_crossings_4h=v['center_crossings_4h'],
                    close_strength=v['close_position'] if d==1 else 1-v['close_position'],
                    signed_body=d*v['body'],distance_width=d*v['distance_width'],
                    bar_range_width=v['bar_range_width'],width_pct=v['width_pct'],
                    structure_break=v['close']>v['previous_high'] if d==1 else v['close']<v['previous_low'])

    @staticmethod
    def decisions(f):
        return dict(baseline=True,aligned_slope=f['slope_2h']>0,local_trend=f['efficiency_2h']>=.3,
                    few_crossings=f['center_crossings_4h']<=2,
                    strong_close=f['close_strength']>=.75 and f['signed_body']>0,
                    closer_entry=f['distance_width']<=1.25,no_spike=f['bar_range_width']<=1.5,
                    active_market=f['width_pct']>=.25,structure_break=f['structure_break'])

    def update(self,bar,position=None,decisions=True):
        previous_width=self.width
        src=(bar.high+bar.low)/2
        self.base=src if self.base is None else self.base+(src-self.base)/16
        movement=bar.high-bar.low
        self.width=movement if self.width is None else self.width+(movement-self.width)/16
        self.bases.append(self.base)
        self.closes.append(bar.close)
        prices=list(self.closes)
        path8=sum(abs(b-a) for a,b in zip(prices,prices[1:]))
        efficiency8=abs(prices[-1]-prices[0])/path8 if path8 else 0.
        last=prices[-9:]
        path2=sum(abs(b-a) for a,b in zip(last,last[1:]))
        efficiency2=abs(last[-1]-last[0])/path2 if path2 else 0.
        center_side=1 if bar.close>self.base else -1 if bar.close<self.base else 0
        self.crossings.append(int(self.center_side*center_side<0))
        if center_side:
            self.center_side=center_side
        upper,lower=self.base+.8*self.width,self.base-.8*self.width
        long=self.upper is not None and self.pc<=self.upper and bar.close>upper
        short=self.lower is not None and self.pc>=self.lower and bar.close<lower
        self.pc,self.upper,self.lower=bar.close,upper,lower
        self.values=dict(slope_2h=self.base-self.bases[0],efficiency_2h=efficiency2,efficiency_8h=efficiency8,
                         center_crossings_4h=sum(self.crossings),close_position=(bar.close-bar.low)/movement if movement else .5,
                         body=bar.close-bar.open,distance_width=(bar.close-self.base)/self.width if self.width else 0,
                         bar_range_width=movement/previous_width if previous_width else 0,width_pct=self.width/bar.close*100,
                         close=bar.close,previous_high=max((b.high for b in self.previous_bars),default=bar.high),
                         previous_low=min((b.low for b in self.previous_bars),default=bar.low))
        self.previous_bars.append(bar)
        self.processed+=1
        if not decisions:
            return None
        action='long' if long else 'short' if short else None
        checks={}
        f={}
        if action:
            d=1 if action=='long' else -1
            f=self.features(d)
            checks=self.decisions(f)
            old_allowed=self.width>0 and d*(bar.close-self.base)<=2*self.width and len(prices)==33 and efficiency8>=.2
            allowed=old_allowed and checks[self.p['entry_filter']]
            if not allowed:
                action='close' if position and position['side']!=action else None
            checks.update(original_entry_allowed=old_allowed,entry_allowed=allowed)
        intent=Intent(action,reason='反向信号或通道突破',profit_protection=ProfitProtection(2,50)) if action else None
        if not self.p['record_indicators']:
            return intent
        return BarResult(intent,values={'中心线':self.base,'宽度基准':self.width,'做多门槛':upper,'做空门槛':lower,
                                        '八小时趋势效率':efficiency8,'两小时趋势效率':efficiency2,
                                        '四小时中心线穿越次数':sum(self.crossings),'宽度占价格百分比':self.values['width_pct'],
                                        '当前有效保护价':position.get('stop') if position else None},
                         checks={'原做多信号':long,'原做空信号':short,**checks},
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
