from math import sin
from types import SimpleNamespace
import pytest
from app.domain.local_backtest import Bar,Intent,ProfitProtection,simulate as original
from app.domain.cloud_adaptive_research_v1 import simulate
from app.domain.cloud_adaptive_types_v1 import AdaptiveIntent,AdaptiveResult
from app.services.local_backtest_strategies import load_strategy,validate_parameters
from scripts.btc_cloud_parameter_study import BASE
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'strategies/trend_cloud_direct_v7.py'


def params(**extra):
    _,s=load_strategy(SOURCE)
    return validate_parameters(s,{**BASE,**extra})


def bars():
    return [Bar(i*900000,100+4*sin(i/19),101+4*sin(i/19),99+4*sin(i/19),100+4*sin(i/19),1) for i in range(1100)]


def test_disabled_matches_original_engine_and_original_strategy_every_field():
    old,_=load_strategy(SOURCE.parent/'trend_cloud_parameters_v4.py')
    new,_=load_strategy(SOURCE)
    expected=original(bars(),old,BASE,warmup=650,step_ms=900000)
    actual=simulate(bars(),new,params(),warmup=650,step_ms=900000)
    assert len(actual['trades'])>5
    assert expected==actual


def test_efficiency_calculation_and_speed_extremes():
    module,_=load_strategy(SOURCE)
    c=module.Calculation(params(adaptive_center=True))
    for i in range(50):c.update(Bar(i,100+i,101+i,99+i,100+i,1),decisions=False)
    assert c.er==pytest.approx(1)
    assert 2/c.alpha-1==pytest.approx(21)
    c=module.Calculation(params(adaptive_center=True))
    for i in range(100):c.update(Bar(i,100,101,99,100,1),decisions=False)
    assert c.er==0 and 2/c.alpha-1==pytest.approx(89)


def test_prefix_observations_unaffected_by_future():
    module,_=load_strategy(SOURCE)
    a=module.Calculation(params(adaptive_center=True,scaled_risk=True,atr_trailing=True,record_indicators=True))
    b=module.Calculation(a.p)
    data=bars()
    expected=[a.update(x,decisions=i>=650) for i,x in enumerate(data[:800])]
    actual=[b.update(x,decisions=i>=650) for i,x in enumerate(data)]
    assert actual[:800]==expected


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_atr_activation_fill_anchor_and_next_bar_ratchet(side,d):
    # Signal close100, fill102/98. Activation4 price units, not4% of fill.
    values=[Bar(0,100,100,100,100,1),
            Bar(60000,100+2*d,max(100+2*d,100+7*d),min(100+2*d,100+7*d),100+6*d,1),
            Bar(120000,100+6*d,max(100+2*d,100+6*d),min(100+2*d,100+6*d),100+3*d,1)]
    def on(c):
        intent=AdaptiveIntent(side,stop_loss_distance=2,activation_distance=4,
            profit_protection=ProfitProtection(2,50)) if len(c.history)==1 else None
        return AdaptiveResult(intent=intent,trailing_distance=2)
    r=simulate(values,SimpleNamespace(on_bar=on),{},warmup=0,step_ms=60000)
    t=r['trades'][0]
    assert t['entry_price']==100+2*d
    assert t['profit_protection']['activation_pct']==pytest.approx(400/(100+2*d))
    assert t['exit_time']==120000 and t['exit_price']==100+5*d
    assert t['exit_reason']=='profit_protection'


def test_atr_expansion_never_loosens_previous_protection():
    values=[Bar(0,100,100,100,100,1),Bar(60000,100,110,100,109,1),
            Bar(120000,109,112,109,110,1),Bar(180000,110,111,107,108,1)]
    def on(c):
        return AdaptiveResult(intent=Intent('long',stop_loss_pct=1,profit_protection=ProfitProtection(2,50)) if len(c.history)==1 else None,
            trailing_distance=2 if len(c.history)<=2 else 20)
    r=simulate(values,SimpleNamespace(on_bar=on),{},warmup=0,step_ms=60000)
    assert r['trades'][0]['exit_price']==108 and r['trades'][0]['exit_time']==180000


def test_entry_filter_never_blocks_opposite_exit():
    module,_=load_strategy(SOURCE)
    c=module.Calculation(params(efficiency_gate=True));found=False
    for i in range(700):
        price=100+(-2 if i%2 else 2)
        x=Bar(i*900000,price,price+.1,price-.1,price,1)
        pos=dict(side='long',stop=None)
        r=c.update(x,pos,decisions=i>=650)
        if c.audit and c.audit[-1]['timestamp']==x.timestamp:
            a=c.audit[-1]
            if a['side']=='short' and not a['efficient']:
                assert r.intent.action=='close';found=True
    assert found
