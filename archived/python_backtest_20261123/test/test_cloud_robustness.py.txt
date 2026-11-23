from collections import deque
from math import sin
from pathlib import Path

import numpy as np
import pytest

from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import inspect_strategy, load_strategy, validate_parameters
from scripts.cloud_robustness_study import bootstrap, pick, stitched

ROOT = Path(__file__).parents[1]
SOURCE = ROOT/'strategies/trend_cloud_robustness_v1.py'


def module_params(**changes):
    m,s = load_strategy(SOURCE)
    return m, validate_parameters(s, {'record_indicators':False, **changes})


@pytest.mark.parametrize('activation,trigger',[(0,.99),(0,.8),(2,.8)])
def test_three_reference_rules_are_exact_replays(activation,trigger):
    m,p = module_params(activation_pct=activation,trigger_mult=trigger)
    old,s = load_strategy(ROOT/'strategies/trend_cloud_profit_protection.py')
    op = validate_parameters(s, {'activation_pct':activation,'giveback_pct':50,'trigger_mult':trigger,'record_indicators':False})
    bars = [Bar(i*900000,100+8*sin(i/17),102+8*sin(i/17),98+8*sin(i/17),100+8*sin(i/17),1) for i in range(1500)]
    new = simulate(bars,m,p,warmup=650)
    original = simulate(bars,old,op,warmup=650)
    assert len(new['trades']) > 10
    assert new['trades'] == original['trades']
    assert new['equity'] == original['equity']


@pytest.mark.parametrize('method,value',[('slow_trend',96),('efficiency',.3),('spacing',16),('alternate',0)])
def test_entry_filters_cannot_block_opposite_signal_exit(method,value):
    m,p = module_params(entry_method=method,method_value=value)
    def calculation():
        c = m.Calculation(p)
        c.base,c.width,c.pc,c.upper,c.lower,c.slow = 100,2,103,102,98,90
        c.processed,c.last_entry_index,c.last_entry_side = 33,32,'short'
        c.closes = deque([98,102]*16+[98],maxlen=33)
        return c
    bar = Bar(34*900000,99,101,97,97.5,1)
    assert calculation().update(bar,{'side':'long'}).action == 'close'
    assert calculation().update(bar,{'side':'short'}) is None
    assert calculation().update(bar,None) is None


def test_warmup_never_creates_phantom_entry_history():
    m,p = module_params(entry_method='alternate')
    c = m.Calculation(p)
    for i in range(650):
        v = 100+8*sin(i/10)
        c.update(Bar(i*900000,v,v+1,v-1,v,1),decisions=False)
    assert c.last_entry_index is None and c.last_entry_side is None


def test_future_prices_do_not_change_prior_signals():
    def run(last):
        m,p = module_params(entry_method='spacing',method_value=16)
        bars = [Bar(i*900000,100+8*sin(i/17),102+8*sin(i/17),98+8*sin(i/17),100+8*sin(i/17),1) for i in range(1000)]
        return simulate(bars+[Bar(1000*900000,last,last+1,last-1,last,1)],m,p,warmup=650,step_ms=900000)
    a,b = run(80),run(200)
    assert [{k:v for k,v in s.items() if k != 'status'} for s in a['signals'] if s['timestamp'] < 1000*900000] == [
        {k:v for k,v in s.items() if k != 'status'} for s in b['signals'] if s['timestamp'] < 1000*900000]
    assert a['equity'][:-1] == b['equity'][:-1]


def test_selection_excludes_neighbors_and_can_choose_cash():
    plan = {'variants':{'a':{'selectable':True},'b':{'selectable':False}}}
    row = dict(return_pct=20,profit_factor=1.2,total_trades=100,return_to_drawdown=2)
    assert pick({'a':row,'b':dict(row,return_pct=1000,return_to_drawdown=100)},plan) == ['a']
    assert pick({'a':dict(row,return_pct=-1)},plan) == []


def test_quarters_compound_and_keep_cross_boundary_drawdown():
    def part(profit,end):
        return dict(report={'initial_cash':10000,'final_equity':10000+profit},
                    equity=[{'timestamp':(end-1)*86400000,'equity':10000},{'timestamp':end*86400000,'equity':10000+profit}],
                    trades=[{'profit':profit,'principal':10000,'quantity':100}])
    r = stitched([('q1',part(2000,1)),('q2',part(-1000,2))])
    assert r['report']['final_equity'] == 10800
    assert r['report']['max_drawdown_pct'] == pytest.approx(10)
    assert r['trades'][1]['profit'] == -1200
    assert sum(r['daily_log_returns']) == pytest.approx(np.log(1.08))


def test_bootstrap_joint_identical_candidates_have_identical_bounds():
    r = np.array([.02,-.01,.01,-.02,0]*15)
    a = bootstrap(np.column_stack([r,r]),r,replicates=100,block=7)
    assert a['fixed_annual_return_simultaneous_lower_95'][0] == a['fixed_annual_return_simultaneous_lower_95'][1]
    assert a['fixed_vs_anchor_annual_relative_return_simultaneous_lower_95'] == [0,0]
    assert a['rolling_annual_return_interval_95'][0] < 0 < a['rolling_annual_return_interval_95'][1]
    assert inspect_strategy(SOURCE.read_bytes(),SOURCE.name).id == SOURCE.stem
