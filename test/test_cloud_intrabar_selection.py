from copy import deepcopy
from math import sin
from types import SimpleNamespace
import pytest
from app.domain.local_backtest import Bar, BarResult, Intent, StopEntry, ProfitProtection, simulate
from app.domain.cloud_intrabar_selection_v1 import ScheduledCloud, past_score, choose
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from pathlib import Path

SOURCE = Path(__file__).parents[1]/'strategies/trend_cloud_intrabar_methods_v3.py'
STEP = 900000


def test_unchanged_reviews_preserve_exact_original_fills_and_protection():
    mod, spec = load_strategy(SOURCE)
    p = validate_parameters(spec, dict(confirmation_level=3,max_wait_bars=2))
    bars=[]; detail={}
    for i in range(950):
        o=100+3*sin(i/11);c=100+3*sin((i+1)/11)
        b=Bar(i*STEP,o,max(o,c)+.3,min(o,c)-.3,c,1);bars.append(b)
        detail[b.timestamp]=[Bar(b.timestamp+j*300000,o+(c-o)*j/3,b.high,b.low,o+(c-o)*(j+1)/3,1/3) for j in range(3)]
    expected=simulate(bars,mod,p,warmup=650,step_ms=STEP,execution_bars=detail,intrabar_profit_protection=True)
    wrapper=ScheduledCloud(mod.Calculation,{'a':p,'b':{**p,'center_length':34}},
        [dict(at=i*STEP,chosen='a') for i in (650,700,800)],start=650*STEP)
    actual=simulate(bars,wrapper,p,warmup=650,step_ms=STEP,execution_bars=detail,intrabar_profit_protection=True)
    assert actual==expected and actual['trades'] and not wrapper.transitions


class Probe:
    def __init__(self,p):self.p=p;self.processed=0;self.waiting=self.active=self.handled_exit=None
    def update(self,bar,position=None,last_exit=None,decisions=True):
        self.processed+=1
        if not decisions:return
        entry=StopEntry(Intent(self.p['side'],stop_loss_pct=10,profit_protection=ProfitProtection(2,50)),100)
        return BarResult(entry_order=entry)


def test_switch_liquidates_next_open_and_does_not_enter_from_old_order():
    bars=[Bar(i*STEP,100,100,100,100,1) for i in range(4)]
    bars[2]=Bar(2*STEP,103,104,99,103,1)
    s=ScheduledCloud(Probe,{'a':{'side':'long'}},[dict(at=0,chosen='a'),dict(at=2*STEP,chosen=None)],start=0)
    r=simulate(bars,s,{},warmup=0,step_ms=STEP)
    assert len(r['trades'])==1
    t=r['trades'][0];assert t['exit_price']==103 and t['exit_time']==2*STEP
    assert [x['reason'] for x in r['signals'] if x['action']=='close']==['parameter_change']
    assert not [x for x in r['signals'] if x.get('order_type')=='stop_entry' and x['timestamp']>=STEP]


def test_new_choice_waits_for_first_completed_candle():
    bars=[Bar(i*STEP,100,100,100,100,1) for i in range(4)]
    s=ScheduledCloud(Probe,{'a':{'side':'long'}},[dict(at=0,chosen=None),dict(at=2*STEP,chosen='a')],start=0)
    r=simulate(bars,s,{},warmup=0,step_ms=STEP)
    assert r['trades'][0]['entry_time']==3*STEP


def test_score_uses_only_known_equity_and_completed_trades():
    r=dict(equity=[dict(timestamp=t,equity=v) for t,v in [(0,100),(900,110),(1800,120),(2700,1)]],trades=[
        dict(entry_time=950,exit_time=1500,exit_phase='intrabar',exit_reason='stop_loss'),
        dict(entry_time=1000,exit_time=1800,exit_phase='open',exit_reason='signal'),
        dict(entry_time=1000,exit_time=1600,exit_phase='intrabar',exit_reason='stop_loss')])
    score=past_score(r,900,1800,step=900,fine_step=300)
    assert score['closed_trades']==1
    changed=deepcopy(r);changed['equity'][-1]['equity']=100000
    changed['trades'].append(dict(entry_time=2000,exit_time=2400,exit_phase='open',exit_reason='signal'))
    assert past_score(changed,900,1800,step=900,fine_step=300)==score
    assert past_score(r,900,1800,step=900,fine_step=300,fallback={900})['closed_trades']==0
    assert choose({'x':score})['chosen'] is None
    assert choose({'x':{**score,'closed_trades':20}})['chosen']=='x'
