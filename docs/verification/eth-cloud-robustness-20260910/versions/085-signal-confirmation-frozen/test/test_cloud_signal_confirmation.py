from pathlib import Path
from math import sin
from types import SimpleNamespace
import pytest
from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters

ROOT=Path(__file__).parents[1]
SOURCE=ROOT/'strategies/trend_cloud_signal_confirmation_v1.py'
STEP=900000


def load(**p):
    m,s=load_strategy(SOURCE)
    return m,validate_parameters(s,{'record_indicators':False,**p})


def b(i,c=100,o=None,h=102,l=98):
    return Bar(i*STEP,c if o is None else o,h,l,c,1)


def primed(**p):
    m,p=load(**p); c=m.Calculation(p)
    for i in range(650): c.update(b(i),decisions=False)
    return c


@pytest.mark.parametrize('level',[1,2,3])
@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_later_close_not_wick_confirms_once_then_stop_cannot_reuse_signal(level,side,d):
    c=primed(confirmation_level=level)
    assert c.update(b(650,100+d*2,o=100,h=104,l=96)) is None
    target=c.waiting['target']
    assert target == (104 if d==1 else 96) if level==2 else target==100+d*2
    # Touch/break by intrabar extreme alone cannot confirm; equal close cannot.
    assert c.update(b(651,target,h=106,l=94)) is None
    result=c.update(b(652,target+d*.5,h=106,l=94))
    assert result.action==side and c.waiting is None
    assert c.update(b(653,target+d*.6,h=106,l=94)) is None


def test_unlimited_wait_and_finite_window_expiry():
    for limit in (0,2):
        c=primed(max_wait_bars=limit)
        c.update(b(650,102,o=100))
        for i in range(651,659):
            assert c.update(b(i,101.8,h=102,l=98)) is None
        r=c.update(b(659,103,h=104,l=98))
        assert (r is not None and r.action=='long') if limit==0 else r is None


@pytest.mark.parametrize('confirm_at',[651,652])
def test_second_or_third_candle_is_allowed(confirm_at):
    c=primed(max_wait_bars=2)
    c.update(b(650,102,o=100))
    for i in range(651,confirm_at): c.update(b(i,101.9))
    assert c.update(b(confirm_at,103,h=104)).action=='long'


def test_same_direction_does_not_replace_origin_but_opposite_does():
    c=primed()
    c.update(b(650,102,o=100))
    origin=c.waiting.copy()
    # Force a same-direction raw crossing while still below remembered target.
    c.pc=100
    assert c.update(b(651,101.9)) is None
    assert c.waiting==origin
    assert c.update(b(652,97,h=102,l=96)) is None
    assert c.waiting['side']=='short' and c.waiting['timestamp']==652*STEP
    assert c.update(b(653,96.5,h=102,l=96)).action=='short'


def test_opposite_exit_is_immediate_but_reverse_entry_waits():
    c=primed()
    position={'side':'short'}
    r=c.update(b(650,102,o=100),position)
    assert r.action=='close' and c.waiting['side']=='long'
    # Simulator will close at next open; confirm at that candle's close.
    assert c.update(b(651,103,h=104),None).action=='long'


def test_far_original_signal_cannot_arm_but_far_opposite_still_exits():
    c=primed()
    r=c.update(b(650,110,h=110,l=98),{'side':'short'})
    assert r.action=='close' and c.waiting is None


def test_holding_emits_no_same_direction_entries():
    c=primed()
    assert c.update(b(650,102,o=100),{'side':'long'}) is None
    assert c.waiting is None


def test_confirmation_blocked_when_too_far_retains_pending():
    c=primed()
    c.update(b(650,102,o=100))
    assert c.update(b(651,110,h=110,l=98)) is None
    assert c.waiting is not None
    assert c.update(b(652,105,h=110,l=98)).action=='long'


def test_original_control_preserves_all_execution_records():
    bars=[b(i,100+8*sin(i/17),h=102+8*sin(i/17),l=98+8*sin(i/17)) for i in range(2500)]
    m,p=load(confirmation_level=0)
    old,s=load_strategy(ROOT/'strategies/trend_cloud_parameters_v4.py')
    oldp=validate_parameters(s,dict(trigger_mult=.4,initial_stop_pct=1,record_indicators=False))
    assert simulate(bars,m,p,warmup=650,step_ms=STEP)==simulate(bars,old,oldp,warmup=650,step_ms=STEP)


def test_prefix_causality_and_next_open_fill():
    bars=[b(i,100+8*sin(i/17),h=102+8*sin(i/17),l=98+8*sin(i/17)) for i in range(900)]
    def replay(data):
        m,p=load(record_indicators=True)
        return simulate(data,m,p,warmup=650,step_ms=STEP)
    full,part=replay(bars),replay(bars[:800])
    assert part['indicators']==full['indicators'][:150]
    signals={s['timestamp']:s for s in full['signals']}
    for t in full['trades']:
        assert signals[t['entry_time']-STEP]['reason']=='原信号积累后收盘确认'
        assert t['entry_price']==bars[t['entry_time']//STEP].open
