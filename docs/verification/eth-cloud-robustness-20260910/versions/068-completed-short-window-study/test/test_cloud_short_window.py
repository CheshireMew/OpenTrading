from copy import deepcopy
from math import sin
from types import SimpleNamespace

import pytest

from app.domain.local_backtest import Bar,Intent,ProfitProtection,simulate as original
from app.domain.cloud_window_research_v1 import simulate
from app.services.local_backtest_strategies import load_strategy
from scripts.cloud_short_window_study import (choose,past_score,merge_choices,seed_arrays,seeded_module,
    candidates,SOURCE,schedule,START,END,WEEK,stamp)


def strategy():
    return SimpleNamespace(on_bar=lambda ctx:Intent('long',stop_loss_pct=1,profit_protection=ProfitProtection(2,50)) if len(ctx.history)==1 else None)


def test_transition_fills_next_actual_open_and_does_not_use_previous_close():
    bars=[Bar(0,100,100,100,100,1),Bar(60000,100,110,100,108,1)]
    r=simulate(bars,strategy(),{},warmup=0,step_ms=60000,transition_bar=Bar(120000,103,120,80,115,1))
    t=r['trades'][0]
    assert t['exit_price']==103 and t['exit_time']==120000 and t['exit_phase']=='open'
    assert t['exit_reason']=='parameter_change' and t['return_pct']==3
    assert r['equity'][-1]['timestamp']==120000 and r['equity'][-1]['equity']==10300


def test_transition_cancels_old_pending_reversal_and_does_not_open_new_trade():
    bars=[Bar(i*60000,100,100,100,100,1) for i in range(2)]
    s=SimpleNamespace(on_bar=lambda c:Intent('long' if len(c.history)==1 else 'short'))
    r=simulate(bars,s,{},warmup=0,step_ms=60000,transition_bar=Bar(120000,105,110,100,108,1))
    assert len(r['trades'])==1 and r['trades'][0]['side']=='long'
    assert r['signals'][-1]['status']=='cancelled_parameter_change'


def test_identical_scheduled_choices_do_not_split_a_trend_or_close_positions():
    ds=[dict(at=0,chosen='a'),dict(at=7,chosen='a'),dict(at=14,chosen='b'),dict(at=21,chosen=None),dict(at=28,chosen=None)]
    assert merge_choices(ds,35)==[
        dict(start=0,end=14,chosen='a',decisions=2),dict(start=14,end=21,chosen='b',decisions=1),
        dict(start=21,end=35,chosen=None,decisions=2)]


def test_low_sample_or_negative_candidates_cannot_win_on_one_large_trade():
    p={'a':dict(closed_trades=1,return_pct=100,log_return=.693),
       'b':dict(closed_trades=20,return_pct=5,log_return=.0488),
       'c':dict(closed_trades=100,return_pct=-1,log_return=-.01)}
    assert choose(p)==dict(chosen='b',eligible=1)
    p['b']['return_pct']=-2
    assert choose(p)==dict(chosen=None,eligible=0)


def test_past_score_excludes_incomplete_round_trips_and_future_bar_exits():
    r=dict(equity=[dict(timestamp=t,equity=v) for t,v in [(0,100),(100,110),(200,120),(300,1000)]],
           trades=[dict(entry_time=-10,exit_time=110,exit_phase='open'),
                   dict(entry_time=110,exit_time=190,exit_phase='intrabar'),
                   dict(entry_time=195,exit_time=200,exit_phase='intrabar')])
    score=past_score(r,100,200,10)
    assert score['closed_trades']==1 and score['return_pct']==pytest.approx(100*(120/110-1))
    u=deepcopy(r);u['equity'][-1]['equity']=.01;u['trades'].append(dict(entry_time=300,exit_time=310,exit_phase='open'))
    assert past_score(u,100,200,10)==score


@pytest.mark.parametrize('n',[34,55,89])
def test_seeded_activation_matches_strategy_warmed_with_every_prior_bar(n):
    p=next(x['parameters'] for x in candidates().values() if x['parameters']['center_length']==n)
    bars=[]
    for i in range(2400):
        v=100+8*sin(i/19)+sin(i/3)
        bars.append(Bar(i*300000,v,v+1,v-1,v,100))
    bases,widths=seed_arrays(bars,p)
    old,_=load_strategy(SOURCE)
    expected=original(bars,old,p,warmup=1200,step_ms=300000)
    new=seeded_module(p,'5m',bars,550,bases,widths)
    actual=simulate(bars[550:],new,p,warmup=650,step_ms=300000)
    assert actual==expected and len(actual['trades'])>5


def test_window_candidates_and_schedules_keep_exit_rules_and_common_dates():
    cs=candidates();assert len(cs)==24
    for c in cs.values():
        p=c['parameters'];assert (p['initial_stop_pct'],p['activation_pct'],p['giveback_pct'],p['atr_stop_mult'],p['reverse_confirm_bars'])==(1,2,50,0,1)
    for update in (1,2,4):
        ds=schedule(update);assert ds[0]==stamp(START) and ds[-1]<stamp(END)
        assert all(b-a==update*WEEK for a,b in zip(ds,ds[1:]))
