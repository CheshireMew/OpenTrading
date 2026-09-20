from pathlib import Path
from math import sin

import pytest

from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters

ROOT = Path(__file__).parents[1]
STEP = 900000
HOUR = 4*STEP


def loaded(name='trend_cloud_intrabar_support_v1', **overrides):
    module, spec = load_strategy(ROOT/'strategies'/f'{name}.py')
    params = validate_parameters(spec, dict(center_length=55, width_length=50,
        trigger_mult=.8, chase_mult=1.5, confirmation_level=3, max_wait_bars=2,
        initial_stop_pct=2, activation_pct=2, giveback_pct=50, **overrides))
    return module, params


def test_disabling_location_filter_preserves_original_trades_and_equity():
    old, params = loaded('trend_cloud_intrabar_methods_v3')
    new, new_params = loaded(support_gate=False)
    bars = []
    for i in range(1500):
        center = 100 + 4*sin(i/13) + 2*sin(i/31)
        bars.append(Bar(i*STEP, center-.15, center+.7, center-.7, center+.15, 1))
    original = simulate(bars, old, params, warmup=650, step_ms=STEP)
    filtered = simulate(bars, new, new_params, warmup=650, step_ms=STEP)
    assert original['report']['total_trades'] > 10
    assert original['trades'] == filtered['trades']
    assert original['equity'] == filtered['equity']
    assert original['report'] == filtered['report']


@pytest.mark.parametrize('side,d', [('long',1), ('short',-1)])
def test_touch_requires_both_distance_and_visit_and_never_future_level(side,d):
    module, _ = loaded()
    at = 100*STEP
    price = 2000
    bar = (Bar(at,2002,2009,2002,2008,1) if d==1 else
           Bar(at,1998,1998,1991,1992,1))
    level = dict(price=price, known_at=at)
    index = 2 if side=='long' else 3
    assert module.location_checks([level],bar,10)[index]
    assert not module.location_checks([dict(level,known_at=at+STEP)],bar,10)[index]
    assert not module.location_checks([],bar,10)[index]
    # A close too far away does not pass, even if the wick visited the level.
    far = Bar(at,2000,2020,1980,2000+d*11,1)
    assert not module.location_checks([level],far,10)[index]
    # Nearby close but no visit within a quarter-width does not pass.
    unvisited = (Bar(at,2008,2009,2004,2008,1) if d==1 else
                 Bar(at,1992,1996,1991,1992,1))
    assert not module.location_checks([level],unvisited,10)[index]


def test_known_levels_match_old_context_and_pivots_wait_two_complete_hours():
    new, _ = loaded()
    old, _ = load_strategy(ROOT/'strategies/trend_cloud_context_v3.py')
    a, b = new.KnownPriceLevels(), old.MarketContext()
    for i in range(650):
        hi = 102 + sin((i//4)/3)
        bar = Bar(i*STEP,100,hi,98-sin((i//4)/5),100,1)
        assert a.known_levels(bar.timestamp) == b.known_levels(bar.timestamp)
        a.update(bar)
        b.update(bar)
        assert all(p['known_at'] >= p['formed_at']+3*HOUR for p in a.pivots)
    assert a.pivots
    # The pivot at hour 2 is only known at hour 5, not during hour 4.
    a = new.KnownPriceLevels()
    for i in range(20):
        hi = [101,102,110,102,101][i//4]
        bar = Bar(i*STEP,100,hi,99,100,1)
        before = a.known_levels(bar.timestamp)
        assert not any(p.get('formed_at')==2*HOUR for p in before)
        a.update(bar)
    assert any(p.get('formed_at')==2*HOUR for p in a.known_levels(5*HOUR))


@pytest.mark.parametrize('side,d', [('long',1), ('short',-1)])
def test_rejected_entry_keeps_opposite_exit_and_passed_signal_waits_without_retouch(side,d):
    module, params = loaded()
    calc = module.Calculation(params)
    for i in range(650):
        calc.update(Bar(i*STEP,100,100.5,99.5,100,1), decisions=False)
    bar = Bar(650*STEP,100,103,97,100+d*1.1,1)
    calc.market.known_levels = lambda at: []
    held = dict(side='short' if d==1 else 'long',entry_time=1,stop=110)
    result = calc.update(bar, position=held)
    assert result.checks['原做多信号' if d==1 else '原做空信号']
    assert result.intent.action == 'close'
    assert result.entry_order is None and calc.waiting is None
    # The original signal passes location; absence of a touch later does not
    # cancel its already-armed two-bar confirmation order.
    calc = module.Calculation(params)
    for i in range(650):
        calc.update(Bar(i*STEP,100,100.5,99.5,100,1), decisions=False)
    calc.market.known_levels = lambda at: [dict(price=100+d*.5,known_at=0)]
    result = calc.update(bar)
    assert result.entry_order is not None and calc.waiting['side']==side
    calc.market.known_levels = lambda at: []
    next_bar = Bar(651*STEP,100+d*1.1,101.2,98.8,100+d*1.05,1)
    result = calc.update(next_bar)
    assert result.entry_order is not None
