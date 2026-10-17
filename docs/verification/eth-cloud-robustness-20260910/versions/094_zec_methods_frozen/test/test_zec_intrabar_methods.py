from pathlib import Path
from types import SimpleNamespace
from math import sin
import pytest
from app.domain.local_backtest import Bar, BarResult, Intent, ProfitProtection, StopEntry, simulate
from app.domain.backtest_history import align_execution_bars
from app.services.local_backtest_strategies import load_strategy,validate_parameters

ROOT=Path(__file__).parents[1]


def strategy(**overrides):
    m,s=load_strategy(ROOT/'strategies/trend_cloud_intrabar_methods_v3.py')
    return m,validate_parameters(s,dict(center_length=144,width_length=31,trigger_mult=1.2,chase_mult=3,
        confirmation_level=3,max_wait_bars=2,activation_pct=1,giveback_pct=35,**overrides))


def seeded(**overrides):
    m,p=strategy(**overrides);c=m.Calculation(p)
    for i in range(650):c.update(Bar(i*1800000,100,100.5,99.5,100,1),decisions=False)
    return c


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_retry_waits_for_stop_candle_extreme_is_used_once_and_cancels_on_opposite(side,d):
    c=seeded(stop_reentry=True)
    signal=c.update(Bar(650*1800000,100,103,97,100+d*2,1))
    assert signal.entry_order.intent.action==side
    stopped=dict(side=side,entry_time=651*1800000,exit_time=651*1800000,exit_reason='stop_loss')
    r=c.update(Bar(651*1800000,100+d*2,104,96,100+d*2,1),last_exit=stopped)
    assert r.checks['止损后准备重进'] and c.waiting['retry']
    assert c.waiting['target']==(104 if d==1 else 96)
    # A repeated last_exit observation must not re-arm/rewrite the retry.
    origin=c.waiting.copy()
    c.update(Bar(652*1800000,100+d*2,103,97,100+d*2,1),last_exit=stopped)
    assert c.waiting['timestamp']==origin['timestamp'] and c.waiting['target']==origin['target']
    twice=dict(side=side,entry_time=653*1800000,exit_time=653*1800000,exit_reason='stop_loss')
    r=c.update(Bar(653*1800000,100+d*2,105,95,100+d*2,1),last_exit=twice)
    assert r.checks['成交后消费信号'] and not r.checks['止损后准备重进'] and c.waiting is None
    c=seeded(stop_reentry=True)
    c.update(Bar(650*1800000,100,103,97,100+d*2,1))
    r=c.update(Bar(651*1800000,100+d*2,104,96,100-d*3,1),last_exit=stopped)
    assert not r.checks['止损后准备重进']
    assert c.waiting is None or c.waiting['side']!=side


@pytest.mark.parametrize('method',[1,2])
def test_volatility_stop_is_known_before_fill_clipped_and_not_widened(method):
    c=seeded(stop_method=method)
    r=c.update(Bar(650*1800000,100,103,97,102,1))
    risk=r.entry_order.intent
    scale=c.width if method==1 else c.atr
    assert risk.stop_loss_pct==pytest.approx(min(2,max(.5,100*1.5*scale/102)))
    assert risk.profit_protection==ProfitProtection(1,35)
    held=dict(side='long',entry_time=651*1800000,stop=100)
    r=c.update(Bar(651*1800000,102,110,95,103,1),position=held)
    assert r.entry_order is None and r.intent is None


def test_direction_filter_blocks_entry_but_never_opposite_exit():
    c=seeded(direction_filter=True)
    # Falling centers while price closes through upper; gate must block the entry.
    c.centers.clear();c.centers.extend([110]*7)
    held=dict(side='short',entry_time=1,stop=103)
    r=c.update(Bar(650*1800000,100,103,97,102,1),position=held)
    assert r.checks['原做多信号'] and r.intent.action=='close' and r.entry_order is None


def sample(actions,fast=False,details=None):
    bars=[Bar(0,100,100,100,100,1),Bar(1800000,100,102,99.5,100.5,6)]
    fine=[Bar(1800000,100,101,99.5,100.9,1),Bar(2100000,100.9,102,100.8,101.8,1),
          Bar(2400000,101.8,101.9,100.8,101,1),Bar(2700000,101,101.1,100.5,100.8,1),
          Bar(3000000,100.8,101,100.5,100.7,1),Bar(3300000,100.7,100.9,100.5,100.5,1)]
    group,check=align_execution_bars(bars[1:],fine,1800000,300000)
    assert check['matched']==1
    return simulate(bars,SimpleNamespace(on_bar=lambda ctx:actions.get(len(ctx.history)-1)),{},warmup=0,
        step_ms=1800000,execution_bars=group if details is None else details,intrabar_profit_protection=fast)


def test_fine_protection_activates_next_fine_bar_but_original_waits_parent_close():
    actions={0:Intent('long',stop_loss_pct=1,profit_protection=ProfitProtection(1,35))}
    slow=sample(actions);fast=sample(actions,True)
    assert slow['trades'][0]['exit_reason']=='end_of_backtest'
    t=fast['trades'][0]
    assert t['exit_time']==2400000 and t['exit_price']==pytest.approx(101.3)
    assert t['exit_reason']=='profit_protection'
    assert len(fast['indicators']) if 'indicators' in fast else True
    assert fast['execution_detail']['profit_protection_update']=='execution_close'


def test_fine_entry_waits_until_later_subcandle_without_new_signal():
    r=sample({0:BarResult(entry_order=StopEntry(Intent('long',stop_loss_pct=1),101.5,103))})
    t=r['trades'][0]
    assert t['entry_time']==2100000 and t['entry_price']==101.5
    assert len(r['signals'])==1


def test_missing_fine_detail_falls_back_identically_for_both_protection_modes():
    actions={0:Intent('long',stop_loss_pct=1,profit_protection=ProfitProtection(1,35))}
    a=sample(actions,False,{});b=sample(actions,True,{})
    assert a['trades']==b['trades'] and a['equity']==b['equity']
    assert a['execution_detail']['fallback_candles']==2


def test_mismatched_or_incomplete_fine_prices_rejected_without_rewriting_signal_candle():
    parent=Bar(0,100,102,98,101,6)
    fine=[Bar(i*300000,100,102,98,101,1) for i in range(6)]
    fine[-1]=Bar(1500000,100,102,98,100,1)
    mapping,check=align_execution_bars([parent],fine,1800000,300000)
    assert not mapping and check['rejected'][0]['reason']=='ohlc_mismatch'
    mapping,check=align_execution_bars([parent],fine[:-1],1800000,300000)
    assert not mapping and check['rejected'][0]['reason']=='missing_fine_bars'
