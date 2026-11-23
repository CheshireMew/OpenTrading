from pathlib import Path
from math import sin
import pytest
from app.domain.local_backtest import Bar,simulate
from app.services.local_backtest_strategies import load_strategy,validate_parameters,inspect_strategy
from strategies.cross_market_trend_v1 import Calculation,STRATEGY
from scripts.cross_market_trend_study import variants,choose,safe_start,DAY

ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'strategies/cross_market_trend_v1.py'
def params(**kw):
    _,meta=load_strategy(SOURCE)
    return validate_parameters(meta,dict(record_indicators=False,**kw))
def b(i,c,h=None,l=None):return Bar(i*DAY,c,max(c,h) if h else c+1,min(c,l) if l else c-1,c,1)


def test_strategy_is_available_through_project_catalog():
    meta=inspect_strategy(SOURCE.read_bytes(),SOURCE.name)
    assert meta.id==SOURCE.stem and meta.warmup_bars==200
    vs=variants();assert len(vs)==12
    assert {v['timeframe'] for v in vs.values()}=={'4h','1d'}
    assert all(v['parameters']['atr_mult']==3 and v['parameters']['atr_length']==14 for v in vs.values())


def test_breakout_excludes_current_bar_and_uses_strict_close():
    c=Calculation(params(family='breakout',entry_length=5,exit_length=2,atr_length=2))
    for i in range(5):c.update(b(i,100),decisions=False)
    assert c.update(b(5,101,h=120)) is None  # wick does not confirm; equality is not a breakout
    # Highest prior bar is now120; close121 can cross it despite current high130.
    signal=c.update(b(6,121,h=130))
    assert signal.action=='long' and signal.stop_loss_distance==pytest.approx(c.atr*3)


def test_breakout_shorter_exit_can_exit_before_opposite_entry():
    c=Calculation(params(family='breakout',entry_length=5,exit_length=2,atr_length=2))
    for i in range(5):c.update(b(i,100+i,h=110+i,l=90+i),decisions=False)
    # Below last2 lows93/94, but still above last5 low90: exit, not short.
    signal=c.update(b(5,92),{'side':'long'})
    assert signal.action=='close'


@pytest.mark.parametrize('family,extra',[('average',dict(fast_length=2,slow_length=3)),('momentum',dict(entry_length=3))])
def test_first_regime_entry_then_stop_requires_new_regime(family,extra):
    c=Calculation(params(family=family,atr_length=2,**extra))
    for i in range(4):c.update(b(i,100+i),decisions=False)
    assert c.update(b(4,104)).action=='long'
    assert c.update(b(5,105),None) is None  # stopped/flat, same direction
    assert c.update(b(6,90),None).action=='short'


def test_momentum_looks_back_exact_number_of_bars():
    c=Calculation(params(family='momentum',entry_length=3,atr_length=2))
    for i,price in enumerate([100,105,110]):c.update(b(i,price),decisions=False)
    assert c.update(b(3,103)).action=='long'  # compares100, not105
    assert c.update(b(4,101),{'side':'long'}).action=='short'  # compares105


def test_wilder_atr_signal_distance_and_no_profit_target():
    c=Calculation(params(family='momentum',entry_length=2,atr_length=2))
    c.update(b(0,100),decisions=False);c.update(b(1,110),decisions=False)
    signal=c.update(b(2,112))
    assert c.atr==pytest.approx(4.75)  # TR2,11,3; ATR6.5 then4.75
    assert signal.stop_loss_distance==14.25
    assert signal.profit_protection is None and signal.take_profit_pct is None


@pytest.mark.parametrize('family',['breakout','average','momentum'])
def test_no_future_bar_changes_past_trades_or_signals(family):
    bars=[b(i,100+20*sin(i/13)+i/100) for i in range(400)]
    p=params(family=family);m,_=load_strategy(SOURCE);old=simulate(bars[:300],m,p,warmup=200,step_ms=DAY)
    m,_=load_strategy(SOURCE);new=simulate(bars,m,p,warmup=200,step_ms=DAY)
    # Ignore artificial end-of-period close and last pending order status.
    completed=[t for t in old['trades'] if t['exit_reason']!='end_of_backtest']
    assert completed==new['trades'][:len(completed)] and len(old['trades'])>0
    clean=lambda s:{k:v for k,v in s.items() if k!='status'}
    assert [clean(s) for s in old['signals']]==[clean(s) for s in new['signals'] if s['timestamp']<=bars[299].timestamp]


def test_selection_excludes_held_asset_and_future_year():
    rows={a:{k:{'train':{'return_pct':v},'future':{'return_pct':1e9}} for k,v in [('x',10.),('y',5.)]} for a in 'abcdef'}
    x=choose(rows,['x','y'],list('abcde'),'train');assert x['selected']=='x'
    rows['f']['y']['train']['return_pct']=1e12;rows['a']['y']['future']['return_pct']=1e15
    assert choose(rows,['x','y'],list('abcde'),'train')==x
    for a in 'abcd':rows[a]['x']['train']['return_pct']=-1;rows[a]['y']['train']['return_pct']=-2
    assert choose(rows,['x','y'],list('abcdef'),'train')['selected'] is None


def test_start_does_not_invent_missing_warmup_or_listing_history():
    rows=[[i*DAY,1,1,1,1,0] for i in range(205)]
    assert safe_start(rows,0,DAY)==200*DAY
    rows.pop(5)
    with pytest.raises(ValueError):safe_start(rows,0,DAY)
