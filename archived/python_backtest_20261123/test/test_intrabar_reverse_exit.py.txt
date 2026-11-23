from pathlib import Path
from math import sin
import pytest
from app.domain.local_backtest import Bar, ProfitProtection
from app.services.local_backtest_strategies import load_strategy, validate_parameters

ROOT=Path(__file__).parents[1]
STEP=14400000


def make(version='trend_cloud_intrabar_exit_v4',**changes):
    m,s=load_strategy(ROOT/'strategies'/f'{version}.py')
    p=validate_parameters(s,dict(center_length=55,width_length=50,trigger_mult=.4,chase_mult=3,
        confirmation_level=3,max_wait_bars=2,initial_stop_pct=2,activation_pct=2,giveback_pct=50,**changes))
    c=m.Calculation(p)
    for i in range(650):c.update(Bar(i*STEP,100,100.5,99.5,100,1),decisions=False)
    return c


def test_default_switch_preserves_original_decisions_with_positions():
    a=make('trend_cloud_intrabar_methods_v3');b=make()
    for i in range(650,800):
        o=100+3*sin(i);close=100+3*sin(i+1)
        bar=Bar(i*STEP,o,max(o,close)+.2,min(o,close)-.2,close,1)
        held=None if i%3==0 else dict(side='long' if i%3==1 else 'short',entry_time=(i-1)*STEP,stop=98)
        assert a.update(bar,position=held)==b.update(bar,position=held)


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_opposite_does_not_exit_or_arm_reversal_and_flat_needs_fresh_signal(side,d):
    c=make(reverse_exit=False)
    held=dict(side=side,entry_time=1,stop=98 if d==1 else 102)
    close=100-2*d
    signal=c.update(Bar(650*STEP,100,103,97,close,1),position=held)
    assert signal.checks['原做空信号' if d==1 else '原做多信号']
    assert signal.intent is None and signal.entry_order is None and c.waiting is None
    stopped=dict(side=side,entry_time=1,exit_time=651*STEP,exit_reason='stop_loss')
    after=c.update(Bar(651*STEP,close,close+.1,close-.1,close,1),last_exit=stopped)
    assert after.intent is None and after.entry_order is None
    fresh=c.update(Bar(652*STEP,close,103,97,100+2*d,1),last_exit=stopped)
    assert fresh.entry_order.intent.action==side
    assert fresh.entry_order.intent.stop_loss_pct==2
    assert fresh.entry_order.intent.profit_protection==ProfitProtection(2,50)


def test_flat_opposite_still_replaces_pending_confirmation():
    c=make(reverse_exit=False)
    a=c.update(Bar(650*STEP,100,103,97,102,1))
    assert a.entry_order.intent.action=='long'
    b=c.update(Bar(651*STEP,102,103,97,98,1))
    assert b.checks['反向取消旧等待'] and b.entry_order.intent.action=='short'
    assert c.waiting['timestamp']==651*STEP
