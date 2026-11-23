from types import SimpleNamespace
from pathlib import Path
from math import sin
import pytest
from app.domain.local_backtest import Bar, Intent, ProfitProtection, StopEntry, BarResult, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters


def run(prices, actions):
    bars=[Bar(i*60000,*p,1) for i,p in enumerate(prices)]
    return simulate(bars,SimpleNamespace(on_bar=lambda c:actions.get(len(c.history)-1)),{},warmup=0,step_ms=60000)


@pytest.mark.parametrize('side,trigger,prices',[('long',105,(100,106,99,101)),('short',95,(100,101,94,99))])
def test_breakout_fills_at_known_level_without_waiting_for_close(side,trigger,prices):
    result=run([(100,110,90,100),prices],{0:BarResult(entry_order=StopEntry(Intent(side),trigger))})
    t=result['trades'][0]
    assert t['entry_time']==60000 and t['entry_price']==trigger and t['entry_phase']=='intrabar'
    assert t['exit_price']==prices[3]


def test_no_retroactive_signal_bar_entry_and_unfilled_order_expires():
    r=run([(100,120,90,100),(100,104,99,102),(102,110,101,108)],
          {0:BarResult(entry_order=StopEntry(Intent('long'),105))})
    assert not r['trades'] and r['signals'][0]['status']=='not_triggered'


@pytest.mark.parametrize('side,trigger,opening,cap',[('long',105,107,110),('short',95,93,90)])
def test_gap_fills_actual_open_but_rejects_gap_past_cap(side,trigger,opening,cap):
    order=StopEntry(Intent(side),trigger,cap)
    r=run([(100,100,100,100),(opening,opening,opening,opening)],{0:BarResult(entry_order=order)})
    assert r['trades'][0]['entry_price']==opening and r['trades'][0]['entry_phase']=='open'
    far=cap+(1 if side=='long' else -1)
    r=run([(100,100,100,100),(far,far,far,far)],{0:BarResult(entry_order=order)})
    assert not r['trades'] and r['signals'][0]['status']=='ignored_price_cap'


@pytest.mark.parametrize('side,trigger,ohlc',[('long',105,(100,110,98,108)),('short',95,(100,102,90,92))])
def test_entry_bar_ambiguous_stop_is_identified_under_both_assumptions(side,trigger,ohlc):
    for policy in ('stop_first','adverse_extreme_before_entry'):
        r=run([(100,100,100,100),ohlc],{0:BarResult(entry_order=StopEntry(Intent(side,1),trigger,ambiguity_policy=policy))})
        t=r['trades'][0]
        assert t['entry_bar_ambiguous'] and t['ambiguous']
        assert (t['exit_reason']=='stop_loss')==(policy=='stop_first')


@pytest.mark.parametrize('side,trigger,ohlc',[('long',105,(100,110,98,100)),('short',95,(100,102,90,100))])
def test_adverse_close_proves_post_entry_stop_under_both_assumptions(side,trigger,ohlc):
    r=run([(100,100,100,100),ohlc],{0:BarResult(entry_order=StopEntry(Intent(side,1),trigger,ambiguity_policy='adverse_extreme_before_entry'))})
    assert r['trades'][0]['exit_reason']=='stop_loss'
    assert not r['trades'][0]['entry_bar_ambiguous']


def test_gap_entry_stop_cannot_be_disregarded():
    r=run([(100,100,100,100),(107,110,102,108)],
          {0:BarResult(entry_order=StopEntry(Intent('long',1),105,ambiguity_policy='adverse_extreme_before_entry'))})
    assert r['trades'][0]['exit_reason']=='stop_loss' and not r['trades'][0]['ambiguous']


def test_close_at_open_precedes_new_intrabar_order():
    r=run([(100,100,100,100),(100,102,98,101),(101,106,100,103)],
          {0:Intent('short'),1:BarResult(Intent('close'),entry_order=StopEntry(Intent('long'),105))})
    assert [(f['action'],f['phase'],f['price']) for f in r['fills']]==[
        ('short','open',100),('close','open',101),('long','intrabar',105),('close','close',103)]


def test_unfilled_reverse_entry_does_not_postpone_close():
    r=run([(100,100,100,100),(100,102,98,101),(101,104,100,103)],
          {0:Intent('short'),1:BarResult(Intent('close'),entry_order=StopEntry(Intent('long'),105))})
    assert len(r['trades'])==1 and r['trades'][0]['exit_price']==101


def test_orders_cannot_add_to_or_reverse_an_existing_position():
    r=run([(100,100,100,100)]*3,{0:Intent('long'),1:BarResult(entry_order=StopEntry(Intent('short'),101))})
    assert len(r['trades'])==1 and r['signals'][1]['status']=='ignored_position'


def test_profit_protection_updates_only_for_next_bar_after_stop_entry():
    r=run([(100,100,100,100),(100,110,99,109),(109,110,106,108)],
          {0:BarResult(entry_order=StopEntry(Intent('long',profit_protection=ProfitProtection(2,50)),105))})
    t=r['trades'][0]
    assert t['exit_time']==120000 and t['exit_price']==107.5 and t['exit_reason']=='profit_protection'


@pytest.mark.parametrize('order',[
    StopEntry(Intent('close'),100),StopEntry(Intent('long'),float('nan')),
    StopEntry(Intent('long'),100,99),StopEntry(Intent('short'),100,101),
    StopEntry(Intent('long',-1),100),StopEntry(Intent('long'),100,ambiguity_policy='guess'),
])
def test_invalid_orders_rejected_at_creation(order):
    with pytest.raises(ValueError,match='K 线 0'):
        run([(100,100,100,100)],{0:BarResult(entry_order=order)})


SOURCE=Path(__file__).parents[1]/'strategies/trend_cloud_intrabar_confirmation_v1.py'


def primed(**p):
    m,s=load_strategy(SOURCE);c=m.Calculation(validate_parameters(s,p))
    for i in range(650): c.update(Bar(i*60000,100,102,98,100,1),decisions=False)
    return c


@pytest.mark.parametrize('side,d',[('long',1),('short',-1)])
def test_strategy_arms_on_signal_and_consumes_same_bar_stopped_fill(side,d):
    c=primed()
    r=c.update(Bar(650*60000,100,104,96,100+d*2,1))
    assert r.entry_order.intent.action==side and r.entry_order.trigger_price==100+d*2.01
    r=c.update(Bar(651*60000,102,104,98,100+d*2,1),last_exit={'side':side,'entry_time':651*60000})
    assert r.checks['成交后消费信号'] and c.waiting is None and r.entry_order is None


def test_finite_window_allows_exactly_next_two_bars_and_opposite_replaces():
    c=primed(max_wait_bars=2)
    c.update(Bar(650*60000,100,104,98,102,1))
    assert c.update(Bar(651*60000,102,104,98,101.9,1)).entry_order is not None
    r=c.update(Bar(652*60000,101.9,104,98,101.8,1))
    assert r.checks['等待过期'] and r.entry_order is None
    c=primed();c.update(Bar(650*60000,100,104,98,102,1))
    old=c.waiting.copy();c.pc=100
    c.update(Bar(651*60000,100,104,98,101.9,1)); assert c.waiting==old
    r=c.update(Bar(652*60000,101.9,104,96,97,1))
    assert r.checks['反向取消旧等待'] and c.waiting['side']=='short'


def test_future_bars_cannot_change_earlier_orders_or_fills():
    bars=[Bar(i*60000,100+5*sin(i/7),102+5*sin(i/7),98+5*sin(i/7),100+5*sin(i/7),1) for i in range(800)]
    def replay(data):
        m,s=load_strategy(SOURCE)
        return simulate(data,m,validate_parameters(s,{}),warmup=650,step_ms=60000)
    full,part=replay(bars),replay(bars[:760])
    assert part['indicators']==full['indicators'][:110]
    assert [f for f in part['fills'] if f['timestamp']<759*60000]==[f for f in full['fills'] if f['timestamp']<759*60000]
