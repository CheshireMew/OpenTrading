from pathlib import Path
from math import sin
import pytest
from app.domain.local_backtest import Bar,simulate
from app.services.local_backtest_strategies import load_strategy,validate_parameters,inspect_strategy
from scripts.cloud_entry_study import annotate,NAMES

ROOT=Path(__file__).parents[1]
SOURCE=ROOT/'strategies/trend_cloud_entry_v2.py'


def bars():
    return [Bar(i*900000,100+8*sin(i/17),101+8*sin(i/17),99+8*sin(i/17),100+8*sin(i/17),1) for i in range(2000)]


def test_original_entry_and_exits_exactly_unchanged():
    new,ns=load_strategy(SOURCE)
    old,os=load_strategy(ROOT/'strategies/trend_cloud_robustness_v1.py')
    a=simulate(bars(),new,validate_parameters(ns,{'record_indicators':False}),warmup=650,step_ms=900000)
    b=simulate(bars(),old,validate_parameters(os,{'entry_method':'efficiency','method_value':.2,'record_indicators':False}),warmup=650,step_ms=900000)
    assert len(a['trades'])>5
    assert a['trades']==b['trades'] and a['equity']==b['equity']
    assert inspect_strategy(SOURCE.read_bytes(),SOURCE.name).id==SOURCE.stem


@pytest.mark.parametrize('method',list(NAMES)[1:])
def test_entry_filter_does_not_delay_opposite_exit(method):
    module,spec=load_strategy(SOURCE)
    p=validate_parameters(spec,{'entry_filter':method,'record_indicators':False})
    c=module.Calculation(p)
    for b in [Bar(i*900000,100,101,99,100,1) for i in range(650)]:
        c.update(b,decisions=False)
    result=c.update(Bar(650*900000,100,104,98,102,1),{'side':'short'})
    assert result.action in ('long','close')
    assert result.profit_protection.activation_pct==2
    assert result.profit_protection.giveback_pct==50


def test_annotation_uses_signal_bar_and_no_entry_bar_high_low():
    module,spec=load_strategy(SOURCE)
    prices=bars()
    result=simulate(prices,module,validate_parameters(spec,{'record_indicators':False}),warmup=650,step_ms=900000)
    t=result['trades'][0]
    a=annotate(prices,{'trades':[t]})[0]
    changed=list(prices)
    i=t['entry_time']//900000
    b=changed[i]
    changed[i]=Bar(b.timestamp,b.open,10000,1,b.close,1)
    z=annotate(changed,{'trades':[t]})[0]
    assert a['features']==z['features'] and a['filters']==z['filters']
    assert a['feature_time']==t['entry_time']-900000


def test_structure_break_excludes_signal_candle_from_prior_extremes():
    m,s=load_strategy(SOURCE)
    c=m.Calculation(validate_parameters(s,{}))
    for i in range(650):
        c.update(Bar(i*900000,100,101,99,100,1),decisions=False)
    c.update(Bar(650*900000,100,110,99,102,1),decisions=False)
    f=c.features(1)
    assert f['structure_break'] is True
    assert c.values['previous_high']==101
    assert f['bar_range_width']==5.5


def test_long_short_features_are_symmetric():
    m,s=load_strategy(SOURCE)
    one=m.Calculation(validate_parameters(s,{})); two=m.Calculation(validate_parameters(s,{}))
    for b in bars()[:660]:
        one.update(b,decisions=False)
        two.update(Bar(b.timestamp,200-b.open,200-b.low,200-b.high,200-b.close,b.volume),decisions=False)
    a=one.features(1); z=two.features(-1)
    for key in ('slope_2h','efficiency_2h','center_crossings_4h','close_strength','signed_body','distance_width','bar_range_width'):
        assert a[key]==pytest.approx(z[key])
    assert a['structure_break']==z['structure_break']
