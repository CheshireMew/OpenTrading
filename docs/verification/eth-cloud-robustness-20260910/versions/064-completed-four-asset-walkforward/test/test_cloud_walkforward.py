"""Causal price-peak stops and chronological neighborhood selection."""
from itertools import product
from math import sin
from types import SimpleNamespace

import pytest

from app.domain.local_backtest import Bar, Intent, ProfitProtection, simulate as original
from app.domain.cloud_protection_research_v1 import simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from scripts.cloud_walkforward_study import SOURCE, BASE, AXES, METHODS, RISKS, key, identity, pick, folds, score_path


def example(prices,side='long',cap=5,extra=None):
    bars=[Bar(i*60000,*p,1) for i,p in enumerate(prices)]
    actions={0:Intent(side,stop_loss_pct=1,profit_protection=ProfitProtection(2,50)),**(extra or {})}
    return simulate(bars,SimpleNamespace(on_bar=lambda c:actions.get(len(c.history)-1)),{},warmup=0,step_ms=60000,peak_price_drawdown_pct=cap)


def test_price_cap_preserves_90_percent_profit_after_price_doubles_without_same_bar_lookahead():
    r=example([(100,100,100,100),(100,200,100,195),(195,196,185,190)])
    t=r['trades'][0]
    assert t['exit_price']==190 and t['return_pct']==90
    assert t['exit_time']==120000 and t['exit_reason']=='price_peak_protection'
    assert r['levels'][0]['stop']==99 and r['levels'][1]['stop']==190


def test_short_cap_uses_trough_price_and_gap_execution_not_entry_relative_distance():
    r=example([(100,100,100,100),(100,100,50,51),(54,55,53,54)],'short')
    assert r['levels'][1]['stop']==52.5
    assert r['trades'][0]['exit_price']==54
    assert r['trades'][0]['return_pct']==46
    assert r['trades'][0]['exit_phase']=='open'


def test_tighter_peak_limit_never_moves_back_out_and_reverse_remains_active():
    r=example([(100,100,100,100),(100,200,100,195),(195,198,191,194),(193,194,192,193)],extra={2:Intent('short')})
    assert r['trades'][0]['exit_reason']=='reversal'
    assert r['trades'][0]['exit_price']==193
    assert [x['stop'] for x in r['levels'] if x['trade_id']==1]==[99,190,190]


def test_disabled_cap_is_exact_original_engine_for_every_protection_and_confirmation():
    bars=[]
    for i in range(1500):
        p=100+10*sin(i/16)+2*sin(i/3)
        bars.append(Bar(i*3600000,p,p+1,p-1,p,100))
    for method in METHODS.values():
        for risk in RISKS.values():
            old,spec=load_strategy(SOURCE);new,_=load_strategy(SOURCE)
            p=validate_parameters(spec,{**BASE,'giveback_pct':method['giveback_pct'],**{k:v for k,v in risk.items() if k!='label'}})
            assert simulate(bars,new,p,warmup=650)==original(bars,old,p,warmup=650)


def sample_past():
    variants={key(p):p for vals in product(*AXES.values()) for p in [{**BASE,**dict(zip(AXES,vals))}]}
    records={identity('1h',k,'g50'):dict(timeframe='1h',entry_key=k,method='g50',score=dict(training_trades=100,train_log_return=.6,median_half_year_log=.1)) for k in variants}
    return variants,records


def test_one_huge_half_year_cannot_rescue_negative_typical_halves():
    variants,records=sample_past()
    for x in records.values():x['score'].update(median_half_year_log=-.1,train_log_return=2)
    assert pick(records,variants)['chosen'] is None
    assert pick(records,variants,'return')['chosen'] is not None


def test_one_parameter_outlier_cannot_rescue_negative_neighbors():
    variants,records=sample_past()
    for x in records.values():x['score'].update(median_half_year_log=-.1,train_log_return=-.6)
    winner=next(iter(records));records[winner]['score'].update(median_half_year_log=.8,train_log_return=4.8)
    assert pick(records,variants)['chosen'] is None


def test_positive_neighborhood_has_five_members_and_small_samples_cannot_be_selected():
    variants,records=sample_past();r=pick(records,variants)
    assert r['chosen'] is not None and len(r['ranking'][0]['neighbors'])==5
    for x in records.values():x['score']['training_trades']=29
    assert pick(records,variants)['chosen'] is None


def test_future_equity_and_exits_cannot_change_training_score_or_selection():
    from scripts.trend_cloud_study import stamp
    f=folds()[0];times=list(map(stamp,f['training_boundaries']))
    equity=[dict(timestamp=t,equity=10000*(1.1**i)) for i,t in enumerate(times)]
    a=dict(equity=equity+[dict(timestamp=times[-1]+3600000,equity=1)],trades=[],_step=3600000)
    b=dict(equity=equity+[dict(timestamp=times[-1]+3600000,equity=1e9)],trades=[dict(exit_time=times[-1]+1,exit_phase='intrabar')],_step=3600000)
    assert score_path(a,f)==score_path(b,f)
    variants,records=sample_past()
    for x in records.values():x['score']={**score_path(a,f),'training_trades':100}
    before=pick(records,variants)
    for x in records.values():x['score']={**score_path(b,f),'training_trades':100}
    assert pick(records,variants)==before


def test_daily_only_enters_after_full_three_year_training_and_no_future_boundaries():
    fs=folds()
    assert len(fs)==6 and sum('all5' in f['pools'] for f in fs)==2
    for f in fs:
        assert f['training_boundaries'][-1]==f['start']<f['end']
        assert len(f['training_boundaries'])==7
        if 'all5' in f['pools']:assert f['train_start']>='2022-10-01'
