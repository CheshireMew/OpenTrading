"""Timeframe adaptation must preserve trading rules and reject interrupted confirmation."""
from dataclasses import replace
from math import sin
import pytest
from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from scripts.cloud_timeframe_study import SOURCE, ROOT, STEPS, candidates
from scripts.alt_cloud_parameter_study import ETH_PARAMETERS
from strategies.trend_cloud_timeframe_v6 import Calculation


def params(**kw):
    _,meta=load_strategy(SOURCE)
    return validate_parameters(meta,{**ETH_PARAMETERS,**kw})


@pytest.mark.parametrize('step',list(STEPS.values()))
def test_confirmation_uses_actual_candle_spacing_and_rejects_gaps(step):
    p=params(reverse_confirm_bars=2,chase_mult=3)
    for gap in (False,True):
        c=Calculation(p,step_ms=step)
        for i in range(650):c.update(Bar(i*step,100,101,99,100,1),decisions=False)
        position={'side':'short','trade_id':7}
        assert c.update(Bar(650*step,100,102,99,102,1),position) is None
        intent=c.update(Bar((652 if gap else 651)*step,102,103,101,102,1),position)
        assert intent is None if gap else intent.action=='long'
        assert c.pending is None


@pytest.mark.parametrize('step',list(STEPS.values()))
def test_same_price_path_preserves_all_trade_returns_across_timeframes(step):
    old,_=load_strategy(ROOT/'strategies/trend_cloud_atr_confirm_v5.py')
    new,_=load_strategy(SOURCE)
    bars=[Bar(i*900000,100+8*sin((i-1)/17),101+8*sin(i/17),99+8*sin(i/17),100+8*sin(i/17),1) for i in range(1200)]
    # Ensure valid OHLC without smoothing away actual crossing opportunities.
    bars=[replace(b,high=max(b.open,b.high,b.close),low=min(b.open,b.low,b.close)) for b in bars]
    p=params(reverse_confirm_bars=2)
    ref=simulate(bars,old,p,warmup=650,step_ms=900000)
    shifted=[replace(b,timestamp=i*step) for i,b in enumerate(bars)]
    actual=simulate(shifted,new,p,warmup=650,step_ms=step)
    assert len(ref['trades'])>5
    assert ref['report']['return_pct']==actual['report']['return_pct']
    for expected,got in zip(ref['trades'],actual['trades'],strict=True):
        for f in ('entry_price','exit_price','side','return_pct','exit_reason'):assert got[f]==expected[f]
        assert got['entry_time']*900000==expected['entry_time']*step
        assert got['exit_time']*900000==expected['exit_time']*step
    if step==900000:assert actual==ref


def test_selected_parameters_are_existing_cloud_versions_not_new_trend_rules():
    selected=candidates()
    assert set(selected)=={'paxg','zec'}
    for a,items in selected.items():
        assert set(items)=={'base','full1','full2','recent1'}
        assert items['base']['parameters']==params()
        assert items['full1']['old_full_return']>=items['full2']['old_full_return']
        assert items['recent1']['old_recent_return']>=max(v['old_recent_return'] for v in items.values())
        assert all('family' not in v['parameters'] and v['origin'] in ('alt','repair') for v in items.values())
