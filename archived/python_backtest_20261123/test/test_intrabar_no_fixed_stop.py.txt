from math import sin
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
import pytest
from app.domain.local_backtest import Bar, simulate, Intent, BarResult
from app.services.local_backtest_strategies import load_strategy, validate_parameters

ROOT=Path(__file__).parents[1]


def load(version,**p):
    m,s=load_strategy(ROOT/f'strategies/trend_cloud_intrabar_confirmation_v{version}.py')
    return m,validate_parameters(s,p)


def test_enabled_stop_retains_v1_full_records():
    bars=[Bar(i*1800000,100+5*sin(i/7),102+5*sin(i/7),98+5*sin(i/7),100+5*sin(i/7),1) for i in range(950)]
    a,pa=load(1,confirmation_level=3,max_wait_bars=2)
    b,pb=load(2,confirmation_level=3,max_wait_bars=2)
    assert simulate(bars,a,pa,warmup=650,step_ms=1800000)==simulate(bars,b,pb,warmup=650,step_ms=1800000)


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_zero_stop_keeps_loss_until_opposite_exit_and_retains_profit_protection(side,d):
    m,p=load(2,confirmation_level=3,max_wait_bars=2,initial_stop_pct=0)
    c=m.Calculation(p)
    for i in range(650): c.update(Bar(i*1800000,100,102,98,100,1),decisions=False)
    signal=c.update(Bar(650*1800000,100,104,96,100+d*2,1))
    order=signal.entry_order
    assert order.intent.action==side and order.intent.stop_loss_pct is None
    assert order.intent.profit_protection.activation_pct==2 and order.intent.profit_protection.giveback_pct==50
    entry=order.trigger_price
    prices=[(100,104,96,100+d*2),
            (entry,max(entry,entry*(1-d*.03)),min(entry,entry*(1-d*.03)),entry*(1-d*.025)),
            (entry*(1-d*.025),entry*(1-d*.025),entry*(1-d*.025),entry*(1-d*.025))]
    actions={0:BarResult(entry_order=order),1:Intent('close',reason='反向信号')}
    bars=[Bar(i*1800000,*r,1) for i,r in enumerate(prices)]
    r=simulate(bars,SimpleNamespace(on_bar=lambda ctx:actions.get(len(ctx.history)-1)),{},warmup=0,step_ms=1800000)
    t=r['trades'][0]
    assert t['exit_time']==3600000 and t['exit_reason']=='signal'
    assert t['return_pct']==pytest.approx(-2.5)
    assert t['stop'] is None


def test_profit_protection_can_exit_without_initial_stop():
    m,p=load(2,confirmation_level=3,max_wait_bars=2,initial_stop_pct=0)
    c=m.Calculation(p)
    for i in range(650): c.update(Bar(i*1800000,100,102,98,100,1),decisions=False)
    order=c.update(Bar(650*1800000,100,104,98,102,1)).entry_order
    e=order.trigger_price
    bars=[Bar(0,100,104,98,102,1),Bar(1800000,e,e*1.04,e*.97,e*1.03,1),Bar(3600000,e*1.03,e*1.035,e*1.01,e*1.025,1)]
    r=simulate(bars,SimpleNamespace(on_bar=lambda ctx:BarResult(entry_order=order) if len(ctx.history)==1 else None),{},warmup=0,step_ms=1800000)
    t=r['trades'][0]
    assert t['exit_time']==3600000 and t['exit_reason']=='profit_protection'
    assert t['return_pct']==pytest.approx(2)
