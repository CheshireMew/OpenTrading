from math import sin
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.domain.local_backtest import Bar, Intent, ProfitProtection, simulate
from app.services.local_backtest_strategies import load_strategy,validate_parameters
from strategies.trend_cloud_atr_confirm_v5 import Calculation
from scripts.alt_cloud_parameter_study import ETH_PARAMETERS

ROOT=Path(__file__).resolve().parents[1];STEP=900000


def params(**kw):return {**ETH_PARAMETERS,'atr_length':14,'atr_stop_mult':0.,'reverse_confirm_bars':1,**kw}
def bar(i,close=100):return Bar(i*STEP,100,max(101,close),min(99,close),close,1)
def calc(**kw):
    c=Calculation(params(**kw))
    for i in range(650):c.update(bar(i),decisions=False)
    return c


def test_disabled_features_match_all_v4_outputs():
    bars=[bar(i,100+8*sin(i/17)) for i in range(2000)]
    old,s=load_strategy(ROOT/'strategies/trend_cloud_parameters_v4.py')
    new,_=load_strategy(ROOT/'strategies/trend_cloud_atr_confirm_v5.py')
    a=simulate(bars,old,ETH_PARAMETERS,warmup=650,step_ms=STEP)
    b=simulate(bars,new,params(),warmup=650,step_ms=STEP)
    assert a==b and len(a['trades'])>5


def test_wilder_atr_includes_previous_close_gap():
    c=Calculation(params(atr_length=2,atr_stop_mult=2))
    c.update(Bar(0,100,101,99,100,1),decisions=False)
    c.update(Bar(STEP,110,111,109,110,1),decisions=False)
    assert c.atr==6.5  # mean of 2 and max(2,11,9)
    c.update(Bar(2*STEP,110,112,109,111,1),decisions=False)
    assert c.atr==4.75


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_absolute_atr_stop_anchors_to_fill_and_is_live_on_entry_bar(side,d):
    def on_bar(ctx):return Intent(side,stop_loss_distance=2,profit_protection=ProfitProtection(2,50)) if len(ctx.history)==1 else None
    result=simulate([bar(0),Bar(STEP,110,114,106,110,1)],SimpleNamespace(on_bar=on_bar),{},warmup=0,step_ms=STEP)
    t=result['trades'][0]
    assert t['entry_price']==110 and t['exit_price']==110-d*2
    assert t['exit_time']==STEP and t['exit_reason']=='stop_loss'


def test_atr_distance_is_signal_value_not_future_entry_bar_range():
    c=calc(atr_stop_mult=3)
    intent=c.update(bar(650,102))
    assert intent.stop_loss_pct is None
    assert intent.stop_loss_distance==pytest.approx(c.atr*3)


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_two_closes_confirm_and_mirror(side,d):
    c=calc(reverse_confirm_bars=2,chase_mult=3)
    pos={'side':'short' if side=='long' else 'long','trade_id':7}
    assert c.update(bar(650,100+2*d),pos) is None
    second=c.update(bar(651,100+2*d),pos)
    assert second.action==side and c.pending is None


def test_failed_second_close_cancels_pending():
    c=calc(reverse_confirm_bars=2)
    pos={'side':'short','trade_id':7}
    assert c.update(bar(650,102),pos) is None
    assert c.update(bar(651,100),pos) is None
    assert c.pending is None


def test_stop_during_confirmation_cancels_delayed_entry():
    c=calc(reverse_confirm_bars=2)
    assert c.update(bar(650,102),{'side':'short','trade_id':7}) is None
    assert c.update(bar(651,102),None) is None
    assert c.pending is None


def test_too_far_confirmation_still_closes_old_position():
    c=calc(reverse_confirm_bars=2,chase_mult=1.5)
    pos={'side':'short','trade_id':7}
    assert c.update(bar(650,102),pos) is None
    assert c.update(bar(651,110),pos).action=='close'


def test_gap_does_not_count_as_consecutive_confirmation():
    c=calc(reverse_confirm_bars=2)
    pos={'side':'short','trade_id':7}
    assert c.update(bar(650,102),pos) is None
    assert c.update(bar(653,102),pos) is None
    assert c.pending is None


@pytest.mark.parametrize('value',[0,-1,float('inf'),float('nan'),True])
def test_invalid_absolute_stop_rejected(value):
    with pytest.raises(ValueError):
        simulate([bar(0),bar(1)],SimpleNamespace(on_bar=lambda c:Intent('long',stop_loss_distance=value)),{},warmup=0)


def test_cannot_specify_both_initial_stop_units():
    with pytest.raises(ValueError):
        simulate([bar(0),bar(1)],SimpleNamespace(on_bar=lambda c:Intent('long',stop_loss_pct=1,stop_loss_distance=1)),{},warmup=0)
