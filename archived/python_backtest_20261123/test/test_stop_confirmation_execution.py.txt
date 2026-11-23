from types import SimpleNamespace

import pytest

from app.domain.local_backtest import Bar, Intent, ProfitProtection, simulate


def run(mode, fine_prices, *, clock='execution', protect=False, side='long', fine_step=300000):
    flat = Bar(0,100,100,100,100,1)
    fine = [Bar(900000+i*fine_step,*row,1) for i,row in enumerate(fine_prices)]
    bars = [flat]
    detail = {0:[flat]}
    for i in range(0,len(fine),3):
        rows=fine[i:i+3]
        b=Bar(rows[0].timestamp,rows[0].open,max(x.high for x in rows),min(x.low for x in rows),rows[-1].close,3)
        bars.append(b);detail[b.timestamp]=rows
    intent=Intent(side,stop_loss_pct=1,stop_loss_confirmation=mode,stop_confirmation_clock=clock,
                  profit_protection=ProfitProtection(2,50) if protect else None)
    strategy=SimpleNamespace(on_bar=lambda c:intent if len(c.history)==1 else None)
    return simulate(bars,strategy,{},warmup=0,step_ms=900000,execution_bars=detail,
                    execution_step_ms=fine_step,intrabar_profit_protection=protect)


@pytest.mark.parametrize('mode,expected,phase,duration',[
    ('next_bar_open',97,'open',5),('next_bar_touch',97,'open',5),('next_bar_close',96,'close',10)])
def test_confirmation_on_next_five_minutes_not_next_fifteen(mode,expected,phase,duration):
    r=run(mode,[(100,101,98,98),(97,99,95,96),(96,110,96,105)])
    t=r['trades'][0]
    assert t['exit_time']==1200000 and t['exit_price']==expected
    assert t['exit_resolution_ms']==300000 and t['duration_minutes']==duration
    assert t['exit_phase']==phase
    event=next(e for e in r['events'] if e['event']=='exit')
    assert event['timestamp']==1200000+(300000 if phase=='close' else 0)
    mark=next(p for p in r['execution_equity'] if p['timestamp']==1500000)
    assert mark['equity']==pytest.approx(10000*(1+(expected-100)/100))


@pytest.mark.parametrize('mode,expected',[
    ('next_bar_open',101),('next_bar_touch',99),('next_bar_close',101)])
def test_recovery_checks_only_declared_open_touch_or_close(mode,expected):
    r=run(mode,[(100,101,98,100),(100,102,97,101),(101,103,100,101)])
    assert r['trades'][0]['exit_price']==expected


def test_short_close_waits_five_minutes_and_uses_actual_close():
    r=run('next_bar_close',[(100,102,99,102),(102,104,101,103),(103,103,100,100)],side='short')
    assert r['trades'][0]['return_pct']==pytest.approx(-3)
    assert r['trades'][0]['duration_minutes']==10


def test_five_minute_wait_survives_fifteen_minute_boundary():
    r=run('next_bar_touch',[(100,101,100,100),(100,101,100,100),(100,100,98,100),
                           (100,101,98,100),(100,101,100,100),(100,101,100,100)])
    assert r['trades'][0]['exit_time']==1800000
    assert r['trades'][0]['exit_reason']=='stop_loss'


def test_parent_close_does_not_finish_an_execution_wait_prematurely():
    r=run('next_bar_close',[(100,101,100,100),(100,101,100,100),(100,100,98,98),
                           (98,101,97,100),(100,101,100,100),(100,101,100,100)])
    assert r['trades'][0]['exit_reason']=='end_of_backtest'
    assert r['trades'][0]['exit_price']==100


def test_five_minute_profit_protection_acts_before_parent_close():
    r=run('next_bar_close',[(100,104,100,103),(103,103,101,101),(101,110,100,110)],protect=True)
    t=r['trades'][0]
    assert t['exit_price']==102 and t['exit_reason']=='profit_protection'
    assert t['exit_time']==1200000


def test_fixed_confirmation_is_checked_before_protection_calculated_at_same_close():
    r=run('next_bar_close',[(100,101,98,100),(100,110,97,98),(98,100,97,99)],protect=True)
    t=r['trades'][0]
    assert t['exit_price']==98 and t['exit_reason']=='stop_loss'


def test_signal_clock_default_retains_fifteen_minute_wait():
    r=run('next_bar_touch',[(100,101,98,98),(98,99,95,96),(96,101,96,100),
                           (100,101,98,100),(100,101,100,100),(100,101,100,100)],clock='signal')
    assert r['trades'][0]['exit_time']==1800000


def test_execution_clock_requires_execution_data():
    intent=Intent('long',stop_loss_pct=1,stop_loss_confirmation='next_bar_close',stop_confirmation_clock='execution')
    strategy=SimpleNamespace(on_bar=lambda c:intent if len(c.history)==1 else None)
    with pytest.raises(ValueError,match='细周期成交行情'):
        simulate([Bar(0,100,100,100,100,1),Bar(900000,100,101,98,99,1)],strategy,{},warmup=0,step_ms=900000)


def test_v2_signal_clock_preserves_v1_trade_records():
    import math
    from pathlib import Path
    from app.services.local_backtest_strategies import load_strategy, validate_parameters
    bars=[]
    for i in range(500):
        o=100+math.sin(i/6)*4;c=100+math.sin((i+1)/6)*4
        bars.append(Bar(i*900000,o,max(o,c)+1,min(o,c)-1,c,1))
    for mode in ('immediate','next_bar_open','next_bar_touch','next_bar_close'):
        results=[]
        for version in ('v1','v2'):
            strategy,spec=load_strategy(Path(f'strategies/trend_cloud_stop_confirmation_{version}.py'))
            p=validate_parameters(spec,{'stop_confirmation':mode,'stop_range_lock':True})
            results.append(simulate(bars,strategy,p,warmup=100,step_ms=900000))
        assert results[0]['trades']==results[1]['trades']
        assert results[0]['equity']==results[1]['equity']
