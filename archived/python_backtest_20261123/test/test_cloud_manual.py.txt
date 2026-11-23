from math import sin
from pathlib import Path
import pytest
from app.domain.local_backtest import Bar,simulate
from app.services.local_backtest_strategies import load_strategy,validate_parameters,inspect_strategy
from scripts.cloud_manual_study import select

ROOT=Path(__file__).parents[1]
SOURCE=ROOT/'strategies/trend_cloud_manual_v1.py'


def calculation(**changes):
    m,s=load_strategy(SOURCE)
    p=validate_parameters(s,{'record_indicators':False,**changes})
    c=m.Calculation(p)
    for i in range(650):
        c.update(Bar(i*900000,100,101,99,100,1),decisions=False)
    return c


def b(i,close,high=103,low=100):
    return Bar(i*900000,101,high,low,close,1)


def test_cross_reference_reproduces_legacy_efficiency_strategy():
    new,ns=load_strategy(SOURCE)
    old,os=load_strategy(ROOT/'strategies/trend_cloud_robustness_v1.py')
    bars=[Bar(i*900000,100+8*sin(i/17),101+8*sin(i/17),99+8*sin(i/17),100+8*sin(i/17),1) for i in range(2000)]
    a=simulate(bars,new,validate_parameters(ns,{'record_indicators':False}),warmup=650,step_ms=900000)
    z=simulate(bars,old,validate_parameters(os,{'entry_method':'efficiency','method_value':.2,'record_indicators':False}),warmup=650,step_ms=900000)
    assert len(a['trades'])>5
    assert a['trades']==z['trades'] and a['equity']==z['equity']
    assert inspect_strategy(SOURCE.read_bytes(),SOURCE.name).id==SOURCE.stem


def test_confirmation_waits_two_closes_and_opposite_signal_exits_immediately():
    c=calculation(entry_mode='confirm',efficiency_threshold=0)
    first=c.update(b(650,102),{'side':'short'})
    assert first.action=='close'
    assert c.update(b(651,102)).action=='long'


def test_confirmation_cancelled_when_price_returns_inside_band():
    c=calculation(entry_mode='confirm',efficiency_threshold=0)
    assert c.update(b(650,102)) is None
    assert c.update(b(651,100)) is None
    assert c.pending is None
    assert c.update(b(652,102)) is None


def test_retest_cannot_enter_on_original_breakout_candle():
    c=calculation(entry_mode='retest',efficiency_threshold=0)
    assert c.update(b(650,102)) is None
    assert c.update(b(651,102)).action=='long'


def test_retest_expires_without_a_touch():
    c=calculation(entry_mode='retest',retest_bars=1,efficiency_threshold=0)
    assert c.update(b(650,102)) is None
    assert c.update(b(651,103,104,102.8)) is None
    assert c.update(b(652,102)) is None
    assert c.pending is None


@pytest.mark.parametrize('mode',['confirm','retest'])
def test_filters_never_block_raw_opposite_exit(mode):
    c=calculation(entry_mode=mode,efficiency_threshold=.9)
    r=c.update(b(650,102),{'side':'short'})
    assert r.action=='close'


def test_profit_rank_cannot_override_win_count_requirement():
    base=dict(wins=60,losses=40,return_pct=10,total_trades=100,return_to_drawdown=2)
    assert select({'valid':base,'more_profit':dict(base,wins=30,losses=70,return_pct=1000,return_to_drawdown=20)})==['valid']
    assert select({'none':dict(base,return_pct=-1)})==[]


def test_future_prices_do_not_change_past_entries():
    def run(last):
        m,s=load_strategy(SOURCE)
        p=validate_parameters(s,{'entry_mode':'retest','activation_pct':.5,'record_indicators':False})
        bars=[Bar(i*900000,100+8*sin(i/17),101+8*sin(i/17),99+8*sin(i/17),100+8*sin(i/17),1) for i in range(1300)]
        return simulate(bars+[Bar(1300*900000,last,last+1,last-1,last,1)],m,p,warmup=650,step_ms=900000)
    a,z=run(20),run(200)
    assert a['equity'][:-1]==z['equity'][:-1]
    assert [s['timestamp'] for s in a['signals'] if s['timestamp']<1300*900000]==[s['timestamp'] for s in z['signals'] if s['timestamp']<1300*900000]
