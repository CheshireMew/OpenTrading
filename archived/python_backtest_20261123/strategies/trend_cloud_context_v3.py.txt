"""Add known support/resistance, completed-hour momentum and four-hour trend."""
from collections import deque
from app.domain.local_backtest import BarResult,Intent,ProfitProtection,TrendCloud

STRATEGY = {'id': 'trend_cloud_context_v3',
 'name': '趋势通道：支撑阻力、动量与趋势 v3',
 'description': '保留原通道入场与退出；分别或组合加入已确认的一小时支撑阻力、一小时 RSI 动量、四小时趋势。',
 'api_version': '1',
 'warmup_bars': 650,
 'parameters': {'filter_mask': {'type': 'int',
                                'default': 7,
                                'min': 0,
                                'max': 7,
                                'label': '过滤组合',
                                'options': [{'value': 0, 'label': '无'},
                                            {'value': 1, 'label': '支撑阻力'},
                                            {'value': 2, 'label': '动量'},
                                            {'value': 3, 'label': '支撑阻力＋动量'},
                                            {'value': 4, 'label': '趋势'},
                                            {'value': 5, 'label': '支撑阻力＋趋势'},
                                            {'value': 6, 'label': '动量＋趋势'},
                                            {'value': 7, 'label': '全部三项'}]},
                'support_rule': {'type': 'str',
                                 'default': 'both',
                                 'label': '支撑阻力检查',
                                 'options': [{'value': 'both', 'label': '位置与前方空间'},
                                             {'value': 'room', 'label': '前方空间'},
                                             {'value': 'touch', 'label': '入场位置'}]},
                'record_indicators': {'type': 'bool', 'default': True, 'label': '保存当时可见的关键价位和条件'}},
 'rules': ['保留原通道入场与退出；分别或组合加入已确认的一小时支撑阻力、一小时 RSI 动量、四小时趋势。', '包含已确认的跨周期支撑阻力，保留原有 650 根上下文下限；均线更长时继续增加预热。'],
 'warmup_rule': {'version': '1',
                 'seed_weight_tolerance': 1e-08,
                 'minimum_bars': 1,
                 'terms': [{'kind': 'window', 'period': 650, 'extra_bars': 0, 'enabled_when': []}],
                 'explanation': '按当前参数取各指标所需历史的最大值。EMA／RMA 初始值权重降至 1e-8 以下，再覆盖已声明回看窗口；这是数值初始化标准，不保证价格或信号完全相同。'}}
STEP=900000
HOUR=3600000


class CompletedBars:
    """Aggregate UTC bars, publish only complete buckets; discard initial partial."""
    def __init__(self,period):
        self.period=period
        self.pending=None

    def update(self,b):
        start=b.timestamp//self.period*self.period
        p=self.pending
        if p is None or p['timestamp']!=start:
            p=dict(timestamp=start,open=b.open,high=b.high,low=b.low,close=b.close,
                   count=1,valid=b.timestamp==start,last=b.timestamp)
        else:
            p.update(high=max(p['high'],b.high),low=min(p['low'],b.low),close=b.close,
                     count=p['count']+1,valid=p['valid'] and b.timestamp==p['last']+STEP,last=b.timestamp)
        self.pending=p
        if b.timestamp+STEP==start+self.period:
            self.pending=None
            if p['valid'] and p['count']==self.period//STEP:
                return {k:p[k] for k in ('timestamp','open','high','low','close')}|{'known_at':start+self.period}
        return None


class MarketContext:
    def __init__(self):
        self.hour=CompletedBars(HOUR)
        self.four=CompletedBars(4*HOUR)
        self.day=CompletedBars(24*HOUR)
        self.hour_history=deque(maxlen=5)
        self.four_closes=deque(maxlen=24)
        self.pivots=deque()
        self.previous_day=None
        self.last_hour_close=None
        self.hour_known_at=self.four_known_at=None
        self.gains=[]
        self.losses=[]
        self.average_gain=self.average_loss=None
        self.rsi=self.previous_rsi=None
        self.sma20=self.sma20_previous4=self.last_four_close=None

    def known_levels(self,at):
        cutoff=at-120*HOUR
        while self.pivots and self.pivots[0]['known_at']<cutoff:
            self.pivots.popleft()
        levels=[dict(p) for p in self.pivots if p['known_at']<=at]
        if self.previous_day and self.previous_day['known_at']<=at:
            levels.extend(dict(price=self.previous_day[k],known_at=self.previous_day['known_at'],kind='previous_day_'+k)
                          for k in ('high','low'))
        return levels

    def update(self,b):
        h=self.hour.update(b)
        if h:
            self.hour_known_at=h['known_at']
            if self.last_hour_close is not None:
                change=h['close']-self.last_hour_close
                gain,loss=max(change,0),max(-change,0)
                if self.average_gain is None:
                    self.gains.append(gain); self.losses.append(loss)
                    if len(self.gains)==14:
                        self.average_gain=sum(self.gains)/14
                        self.average_loss=sum(self.losses)/14
                else:
                    self.average_gain=(13*self.average_gain+gain)/14
                    self.average_loss=(13*self.average_loss+loss)/14
                if self.average_gain is not None:
                    self.previous_rsi=self.rsi
                    total=self.average_gain+self.average_loss
                    self.rsi=100*self.average_gain/total if total else 50.
            self.last_hour_close=h['close']
            self.hour_history.append(h)
            if len(self.hour_history)==5:
                window=list(self.hour_history)
                pivot=window[2]
                others=window[:2]+window[3:]
                if all(pivot['high']>v['high'] for v in others):
                    self.pivots.append(dict(price=pivot['high'],known_at=h['known_at'],formed_at=pivot['timestamp'],kind='hour_high'))
                if all(pivot['low']<v['low'] for v in others):
                    self.pivots.append(dict(price=pivot['low'],known_at=h['known_at'],formed_at=pivot['timestamp'],kind='hour_low'))
        f=self.four.update(b)
        if f:
            self.four_known_at=f['known_at']
            self.last_four_close=f['close']
            self.four_closes.append(f['close'])
            v=list(self.four_closes)
            if len(v)>=20:
                self.sma20=sum(v[-20:])/20
            if len(v)==24:
                self.sma20_previous4=sum(v[:20])/20
        day=self.day.update(b)
        if day:
            self.previous_day=day


class Calculation:
    def __init__(self,p):
        self.p=p
        if p['support_rule'] not in ('both','room','touch'):
            raise ValueError('Unknown support rule')
        self.processed=0
        self.base=self.width=self.pc=self.upper=self.lower=None
        self.closes=deque(maxlen=33)
        self.market=MarketContext()
        self.features={}

    @staticmethod
    def choices(f):
        s,m,t=f['support'],f['momentum'],f['trend']
        return dict(baseline=True,support=s,momentum=m,trend=t,support_momentum=s and m,
                    support_trend=s and t,momentum_trend=m and t,all_three=s and m and t,
                    support_room=f['room'],support_touch=f['touch'])

    def update(self,b,position=None,decisions=True):
        # Price levels used for touches must already exist at signal candle OPEN.
        levels=self.market.known_levels(b.timestamp)
        self.market.update(b)
        m=self.market
        src=(b.high+b.low)/2
        self.base=src if self.base is None else self.base+(src-self.base)/16
        movement=b.high-b.low
        self.width=movement if self.width is None else self.width+(movement-self.width)/16
        upper,lower=self.base+.8*self.width,self.base-.8*self.width
        long=self.upper is not None and self.pc<=self.upper and b.close>upper
        short=self.lower is not None and self.pc>=self.lower and b.close<lower
        self.pc,self.upper,self.lower=b.close,upper,lower
        self.closes.append(b.close)
        prices=list(self.closes)
        path=sum(abs(y-x) for x,y in zip(prices,prices[1:]))
        er=abs(prices[-1]-prices[0])/path if path else 0.
        support=max((v['price'] for v in levels if v['price']<=b.close),default=None)
        resistance=min((v['price'] for v in levels if v['price']>=b.close),default=None)
        known=max((v['known_at'] for v in levels),default=None)
        self.features={}
        for side,d in (('long',1),('short',-1)):
            behind,ahead=(support,resistance) if d==1 else (resistance,support)
            behind_distance=d*(b.close-behind)/self.width if behind is not None and self.width else None
            ahead_distance=d*(ahead-b.close)/self.width if ahead is not None and self.width else None
            touch=bool(behind_distance is not None and 0<behind_distance<=1 and
                       (b.low<=behind+.25*self.width if d==1 else b.high>=behind-.25*self.width))
            room=bool(levels and self.width>0 and (ahead_distance is None or ahead_distance>=2))
            momentum=bool(m.rsi is not None and m.previous_rsi is not None and
                          (m.rsi>=55 if d==1 else m.rsi<=45) and d*(m.rsi-m.previous_rsi)>0)
            trend=bool(m.sma20_previous4 is not None and d*(m.last_four_close-m.sma20)>0 and d*(m.sma20-m.sma20_previous4)>0)
            self.features[side]=dict(support=touch and room,touch=touch,room=room,momentum=momentum,trend=trend,
                                    nearest_support=support,nearest_resistance=resistance,behind_distance_width=behind_distance,
                                    ahead_distance_width=ahead_distance,levels_known_at=known,level_count=len(levels),
                                    rsi=m.rsi,previous_rsi=m.previous_rsi,hour_known_at=m.hour_known_at,
                                    four_known_at=m.four_known_at,four_close=m.last_four_close,four_sma20=m.sma20,
                                    four_sma20_previous4=m.sma20_previous4,original_efficiency=er)
        self.processed+=1
        if not decisions:
            return None
        raw='long' if long else 'short' if short else None
        action=raw
        allowed=False
        if raw:
            d=1 if raw=='long' else -1
            f=self.features[raw]
            mask=self.p['filter_mask']
            sr=f[{'both':'support','room':'room','touch':'touch'}[self.p['support_rule']]]
            allowed=bool(self.width>0 and d*(b.close-self.base)<=2*self.width and len(prices)==33 and er>=.2 and
                         (not mask&1 or sr) and (not mask&2 or f['momentum']) and (not mask&4 or f['trend']))
            if not allowed:
                action='close' if position and position['side']!=raw else None
        intent=Intent(action,reason='反向信号或通道突破',profit_protection=ProfitProtection(2,50)) if action else None
        if not self.p['record_indicators']:
            return intent
        return BarResult(intent,values={'中心线':self.base,'宽度基准':self.width,'做多门槛':upper,'做空门槛':lower,
                                        '最近已知支撑':support,'最近已知阻力':resistance,'一小时 RSI14':m.rsi,
                                        '上一小时 RSI14':m.previous_rsi,'四小时 SMA20':m.sma20,
                                        '十六小时前的四小时 SMA20':m.sma20_previous4,'八小时趋势效率':er,
                                        '当前有效保护价':position.get('stop') if position else None},
                         checks={'原做多信号':long,'原做空信号':short,'允许入场':allowed,
                                 **{('做多' if side=='long' else '做空')+name:f[key]
                                    for side,f in self.features.items() for key,name in (('touch','位置合适'),('room','前方空间足够'),('momentum','动量支持'),('trend','趋势支持'))}},
                         cloud=TrendCloud(self.base+.45*self.width,self.base-.45*self.width,b.close>self.base))


_calculation=None


def on_bar(context):
    global _calculation
    if _calculation is None or _calculation.processed>=len(context.history):
        _calculation=Calculation(context.parameters)
    result=None
    for i in range(_calculation.processed,len(context.history)):
        result=_calculation.update(context.history[i],context.position,decisions=i==len(context.history)-1)
    return result
