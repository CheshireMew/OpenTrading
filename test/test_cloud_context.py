from pathlib import Path
from math import sin
import pytest
from app.domain.local_backtest import Bar,simulate
from app.services.local_backtest_strategies import load_strategy,validate_parameters,inspect_strategy

ROOT=Path(__file__).parents[1]
SOURCE=ROOT/'strategies/trend_cloud_context_v3.py'
STEP=900000


def load(**p):
    m,s=load_strategy(SOURCE)
    return m,validate_parameters(s,{'record_indicators':False,**p})


def bar(i,price=100):
    return Bar(i*STEP,price,price+1,price-1,price,1)


def prices():
    return [bar(i,100+8*sin(i/17)) for i in range(2000)]


def test_baseline_exact_and_strategy_inspectable():
    m,p=load(filter_mask=0)
    old,s=load_strategy(ROOT/'strategies/trend_cloud_robustness_v1.py')
    a=simulate(prices(),m,p,warmup=650,step_ms=STEP)
    b=simulate(prices(),old,validate_parameters(s,{'entry_method':'efficiency','method_value':.2,'record_indicators':False}),warmup=650,step_ms=STEP)
    assert len(a['trades'])>5
    assert a['trades']==b['trades'] and a['equity']==b['equity']
    assert inspect_strategy(SOURCE.read_bytes(),SOURCE.name).id==SOURCE.stem


@pytest.mark.parametrize('mask',range(8))
def test_filters_never_block_opposite_exit(mask):
    m,p=load(filter_mask=mask)
    c=m.Calculation(p)
    for i in range(650):
        c.update(bar(i),decisions=False)
    r=c.update(Bar(650*STEP,100,104,98,102,1),{'side':'short'})
    assert r.action in ('long','close')
    assert r.profit_protection.activation_pct==2 and r.profit_protection.giveback_pct==50


@pytest.mark.parametrize('period',[3600000,14400000,86400000])
def test_only_complete_contiguous_buckets_are_published(period):
    m,_=load(); n=period//STEP
    a=m.CompletedBars(period)
    assert all(a.update(bar(i)) is None for i in range(1,n))
    assert all(a.update(bar(i)) is None for i in range(n,2*n-1))
    completed=a.update(bar(2*n-1,102))
    assert completed['timestamp']==period and completed['known_at']==2*period and completed['close']==102
    # Missing one interior candle invalidates the whole bucket.
    a=m.CompletedBars(period)
    assert all(a.update(bar(i)) is None for i in range(n) if i!=1)


def test_pivot_waits_for_two_right_hours_and_is_not_backdated():
    m,_=load(); c=m.MarketContext()
    for h,p in enumerate([100,102,110,103,101]):
        for k in range(4):
            c.update(bar(h*4+k,p))
            if h*4+k<19:
                assert c.known_levels((h*4+k+1)*STEP)==[]
    assert c.known_levels(5*3600000-1)==[]
    found=c.known_levels(5*3600000)
    assert len(found)==1 and found[0]['price']==111
    assert found[0]['formed_at']==2*3600000 and found[0]['known_at']==5*3600000


def test_hourly_and_four_hour_values_do_not_follow_unfinished_candles():
    m,_=load(); c=m.MarketContext()
    for b in prices()[:1600]:
        c.update(b)
    before=(c.rsi,c.previous_rsi,c.sma20,c.sma20_previous4,c.hour_known_at,c.four_known_at)
    c.update(Bar(1600*STEP,100,10000,1,9000,1))
    assert (c.rsi,c.previous_rsi,c.sma20,c.sma20_previous4,c.hour_known_at,c.four_known_at)==before


def test_previous_day_stays_fixed_until_day_closes():
    m,_=load(); c=m.MarketContext()
    for i in range(96):
        c.update(bar(i))
    first=dict(c.previous_day)
    for i in range(96,191):
        c.update(bar(i,200))
        assert c.previous_day==first
    assert [p['price'] for p in c.known_levels(191*STEP) if p['kind'].startswith('previous_day')]==[101,99]
    c.update(bar(191,200))
    assert c.previous_day['high']==201 and c.previous_day['known_at']==192*STEP


def test_signal_candle_cannot_touch_a_pivot_first_confirmed_at_its_close():
    m,p=load(); c=m.Calculation(p)
    for h,v in enumerate([100,102,110,103,101]):
        for k in range(4):
            c.update(bar(h*4+k,v),decisions=False)
    assert c.features['short']['level_count']==0
    c.update(bar(20,101),decisions=False)
    assert c.features['short']['nearest_resistance']==111
    assert c.features['short']['levels_known_at']<=20*STEP


def test_mirror_prices_give_symmetric_long_short_filters():
    m,p=load(); a=m.Calculation(p); b=m.Calculation(p)
    for v in prices():
        a.update(v,decisions=False)
        b.update(Bar(v.timestamp,200-v.open,200-v.low,200-v.high,200-v.close,1),decisions=False)
    x=a.features['long']; y=b.features['short']
    assert m.Calculation.choices(x)==m.Calculation.choices(y)
    for k in ('behind_distance_width','ahead_distance_width','original_efficiency'):
        assert x[k]==pytest.approx(y[k])
    assert x['rsi']==pytest.approx(100-y['rsi'])


def test_future_candles_cannot_change_pre_entry_annotation():
    from scripts.cloud_context_study import annotate
    m,p=load(filter_mask=0); data=prices()
    result=simulate(data,m,p,warmup=650,step_ms=STEP)
    t=result['trades'][0]
    a=annotate(data,{'trades':[t]})[0]
    idx=t['entry_time']//STEP
    changed=data[:idx]+[bar(i,1000+i) for i in range(idx,len(data))]
    b=annotate(changed,{'trades':[t]})[0]
    assert a==b and a['feature_time']==t['entry_time']-STEP
    assert a['features']['levels_known_at']<=a['feature_time']
    assert a['features']['hour_known_at']<=t['entry_time']
    assert a['features']['four_known_at']<=t['entry_time']
