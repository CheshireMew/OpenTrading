from pathlib import Path
from math import sin
import pytest
from app.domain.local_backtest import Bar
from app.services.local_backtest_strategies import load_strategy, validate_parameters

ROOT=Path(__file__).parents[1]
STEP=900000


def make(gated=True, original=False):
    name='trend_cloud_intrabar_methods_v3' if original else 'trend_cloud_reverse_after_protection_v5'
    m,s=load_strategy(ROOT/'strategies'/f'{name}.py')
    values=dict(center_length=55,width_length=50,trigger_mult=.8,chase_mult=3,
        confirmation_level=3,max_wait_bars=2,initial_stop_pct=2,activation_pct=2,giveback_pct=50)
    if not original:values['reverse_after_protection']=gated
    c=m.Calculation(validate_parameters(s,values))
    for i in range(650):c.update(Bar(i*STEP,100,100.5,99.5,100,1),decisions=False)
    return c


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_gate_blocks_exit_and_opposite_entry_before_activation(side,d):
    c=make();held=dict(side=side,entry_time=1,stop=98 if d==1 else 102,protection_active=False)
    out=c.update(Bar(650*STEP,100,103,97,100-2*d,1),position=held)
    assert out.checks['原做空信号' if d==1 else '原做多信号']
    assert out.intent is None and out.entry_order is None and c.waiting is None
    assert out.checks['保护前忽略反向']


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_latched_activation_allows_reverse_after_price_falls_below_two_percent(side,d):
    c=make();held=dict(side=side,entry_time=1,stop=98 if d==1 else 102,protection_active=True)
    out=c.update(Bar(650*STEP,100,103,97,100-2*d,1),position=held)
    assert out.intent.action=='close'
    assert out.entry_order.intent.action==('short' if side=='long' else 'long')
    assert out.checks['反向退出已启用']


def test_flat_entry_keeps_initial_stop_and_protection_and_new_position_resets_gate():
    c=make();out=c.update(Bar(650*STEP,100,103,97,102,1))
    assert out.entry_order.intent.stop_loss_pct==2
    assert out.entry_order.intent.profit_protection.activation_pct==2
    assert out.entry_order.intent.profit_protection.giveback_pct==50
    held=dict(side='long',entry_time=651*STEP,stop=99.96,protection_active=False)
    out=c.update(Bar(651*STEP,102,103,97,98,1),position=held)
    assert out.intent is None and out.entry_order is None


def test_switch_off_preserves_all_original_trading_decisions():
    a=make(original=True);b=make(gated=False)
    for i in range(650,820):
        o=100+3*sin(i);close=100+3*sin(i+1)
        bar=Bar(i*STEP,o,max(o,close)+.2,min(o,close)-.2,close,1)
        held=None if i%3==0 else dict(side='long' if i%3==1 else 'short',entry_time=(i-1)*STEP,stop=98)
        x,y=a.update(bar,position=held),b.update(bar,position=held)
        assert x.intent==y.intent and x.entry_order==y.entry_order
        assert x.values==y.values and x.cloud==y.cloud
        assert x.checks=={k:v for k,v in y.checks.items() if k not in ['反向退出已启用','保护前忽略反向']}
