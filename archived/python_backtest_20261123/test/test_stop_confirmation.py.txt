from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.local_backtest import Bar, BarResult, Intent, ProfitProtection, StopEntry, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters


def run(rows, mode, *, side='long', actions=None, **risk):
    bars = [Bar(i * 900000, *row, 1) for i, row in enumerate(rows)]
    actions = actions or {0: Intent(side, stop_loss_pct=1, stop_loss_confirmation=mode, **risk)}
    return simulate(bars, SimpleNamespace(on_bar=lambda c: actions.get(len(c.history)-1)), {},
                    warmup=0, step_ms=900000)


@pytest.mark.parametrize('mode,exit_price', [('immediate', 99), ('next_bar_touch', 99),
    ('next_bar_open', 103), ('next_bar_close', 103)])
def test_recovered_open_and_close_but_repeated_intrabar_touch(mode, exit_price):
    result = run([(100,100,100,100), (100,101,97,100), (100,101,98,100), (100,103,100,103)], mode)
    assert result['trades'][0]['exit_price'] == exit_price
    expected = 900000 if mode == 'immediate' else 1800000 if mode == 'next_bar_touch' else 2700000
    assert result['trades'][0]['exit_time'] == expected


@pytest.mark.parametrize('side,rows,expected', [
    ('long', [(100,100,100,100),(100,101,98,100),(97,98,96,97)], 97),
    ('short', [(100,100,100,100),(100,102,99,100),(103,104,102,103)], 103)])
@pytest.mark.parametrize('mode', ['next_bar_open','next_bar_touch','next_bar_close'])
def test_confirmed_loss_is_not_clamped_to_nominal_one_percent(side, rows, expected, mode):
    trade = run(rows, mode, side=side)['trades'][0]
    assert trade['exit_price'] == expected
    assert trade['return_pct'] == pytest.approx(-3)
    assert trade['exit_reason'] == 'stop_loss'
    assert trade['exit_phase'] == ('close' if mode == 'next_bar_close' else 'open')


def test_defer_uses_parent_bar_not_next_five_minutes():
    bars = [Bar(0,100,100,100,100,1), Bar(900000,100,102,95,100,1), Bar(1800000,100,101,98,100,1)]
    fine = {0:[bars[0]], 900000:[Bar(900000,100,101,98,100,1),Bar(1200000,100,102,95,100,1),Bar(1500000,100,100,100,100,1)],
            1800000:[Bar(1800000,100,101,100,100,1),Bar(2100000,100,100,98,100,1),Bar(2400000,100,100,100,100,1)]}
    strategy = SimpleNamespace(on_bar=lambda c: Intent('long', stop_loss_pct=1,stop_loss_confirmation='next_bar_touch') if len(c.history)==1 else None)
    result = simulate(bars,strategy,{},warmup=0,step_ms=900000,execution_bars=fine,execution_step_ms=300000)
    assert result['trades'][0]['exit_time'] == 2100000
    assert result['trades'][0]['exit_price'] == 99


@pytest.mark.parametrize('mode', ['next_bar_open','next_bar_touch','next_bar_close'])
def test_profit_protection_is_not_delayed(mode):
    result = run([(100,100,100,100),(100,104,98,103),(101,102,100,101)], mode,
                 profit_protection=ProfitProtection(2,50))
    assert result['trades'][0]['exit_reason'] == 'profit_protection'
    assert result['trades'][0]['exit_price'] == 101


def test_reverse_exit_remains_active_while_waiting():
    actions = {0:Intent('long',stop_loss_pct=1,stop_loss_confirmation='next_bar_close'),1:Intent('close')}
    result = run([(100,100,100,100),(100,101,98,100),(100,102,95,96)],'next_bar_close',actions=actions)
    assert result['trades'][0]['exit_reason'] == 'signal'
    assert result['trades'][0]['exit_price'] == 100


def test_stop_pause_blocks_preexisting_reverse_order_in_same_parent_bar():
    actions = {0:Intent('long',stop_loss_pct=1,pause_after_stop=True),
               1:BarResult(Intent('close'),entry_order=StopEntry(Intent('short',stop_loss_pct=1),99.5))}
    result = run([(100,100,100,100),(100,100,100,100),(98,98,96,97)],'immediate',actions=actions)
    assert len(result['trades']) == 1
    assert result['signals'][-1]['status'] == 'ignored_stop_pause'


def calculation(lock=True):
    module,spec = load_strategy(Path('strategies/trend_cloud_stop_confirmation_v1.py'))
    return module.Calculation(validate_parameters(spec,{'stop_range_lock':lock,'chase_mult':10})),module,spec


def test_stop_box_uses_closed_stop_bar_and_waits_for_close_outside():
    calc,_,_=calculation()
    calc.update(Bar(0,100,101,99,100,1))
    exited={'side':'long','entry_time':0,'exit_time':900000,'exit_reason':'stop_loss'}
    first=calc.update(Bar(900000,100,110,90,100,1),last_exit=exited)
    assert first.checks['建立止损区间'] and first.entry_order is None
    wick=calc.update(Bar(1800000,100,115,89,105,1),last_exit=exited)
    assert wick.checks['暂停新入场'] and wick.entry_order is None
    assert wick.values['禁止入场区上沿']==110 and wick.values['禁止入场区下沿']==90
    escaped=calc.update(Bar(2700000,105,112,104,111,1),last_exit=exited)
    assert escaped.checks['收盘离开止损区间'] and escaped.entry_order is not None
    assert escaped.entry_order.intent.action=='long'
    assert escaped.entry_order.trigger_price > 111
    position={'side':'long','entry_time':3600000,'stop':110}
    consumed=calc.update(Bar(3600000,112,114,111,113,1),position=position,last_exit=exited)
    assert consumed.entry_order is None and not consumed.checks['建立止损区间']


def test_disabled_features_preserve_original_trades_and_equity():
    import math
    bars=[]
    for i in range(1000):
        o=100+math.sin(i/6)*4
        c=100+math.sin((i+1)/6)*4
        bars.append(Bar(i*900000,o,max(o,c)+1,min(o,c)-1,c,1))
    old,spec=load_strategy(Path('strategies/trend_cloud_intrabar_methods_v3.py'))
    p=validate_parameters(spec,{'confirmation_level':3,'max_wait_bars':2})
    _,new,newspec=calculation(False)
    a=simulate(bars,old,p,warmup=100,step_ms=900000)
    b=simulate(bars,new,validate_parameters(newspec,p),warmup=100,step_ms=900000)
    assert a['trades'] and a['trades']==b['trades']
    assert a['equity']==b['equity'] and a['signals']==b['signals']


def test_confirmation_must_have_a_fixed_stop():
    with pytest.raises(ValueError,match='初始止损距离'):
        run([(100,100,100,100)],'immediate',actions={0:Intent('long',stop_loss_confirmation='next_bar_close')})
