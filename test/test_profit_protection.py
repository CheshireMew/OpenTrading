from math import sin
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.local_backtest import Bar, Intent, ProfitProtection, simulate
from app.services.local_backtest_strategies import inspect_strategy, load_strategy, validate_parameters


def run(prices, actions):
    bars = [Bar(i*60000, *row, 1) for i, row in enumerate(prices)]
    return simulate(bars, SimpleNamespace(on_bar=lambda c: actions.get(len(c.history)-1)), {}, warmup=0, step_ms=60000)


@pytest.mark.parametrize('side,prices,expected', [
    ('long', [(100,100,100,100), (100,105,95,104), (104,106,102,103)], 103),
    ('short', [(100,100,100,100), (100,105,95,96), (96,98,94,97)], 97),
])
def test_protects_peak_profit_but_does_not_retroactively_fill_activation_bar(side, prices, expected):
    r = run(prices, {0: Intent(side, profit_protection=ProfitProtection(2, 40))})
    t = r['trades'][0]
    assert t['exit_price'] == expected
    assert t['exit_time'] == 120000
    assert t['exit_reason'] == 'profit_protection'
    assert t['profit'] == pytest.approx(300)
    assert r['levels'][0]['stop'] is None
    assert r['levels'][1]['stop'] == expected


def test_line_ratchets_and_gap_fills_at_actual_open():
    r = run([(100,100,100,100), (100,105,99,104), (104,110,103.5,109),
             (109,109,107,108), (104,107,100,105)],
            {0: Intent('long', profit_protection=ProfitProtection(2, 40))})
    assert [v['stop'] for v in r['levels']] == [None, 103, 106, 106]
    assert r['trades'][0]['exit_price'] == 104
    assert r['trades'][0]['exit_phase'] == 'open'


@pytest.mark.parametrize('active,open_price,expected_reason', [(False, 99, 'reversal'), (True, 104, 'reversal'), (True, 102, 'profit_protection')])
def test_either_reversal_or_protection_can_exit_without_requiring_both(active, open_price, expected_reason):
    r = run([(100,100,100,100), (100,105 if active else 101,99,104 if active else 100),
             (open_price,open_price,open_price,open_price)],
            {0: Intent('long', profit_protection=ProfitProtection(2, 40)), 1: Intent('short')})
    assert r['trades'][0]['exit_price'] == open_price
    assert r['trades'][0]['exit_reason'] == expected_reason
    assert r['trades'][1]['side'] == 'short'
    assert r['trades'][1]['entry_price'] == open_price
    assert len([f for f in r['fills'] if f['action'] == 'close' and f['trade_id'] == 1]) == 1


def test_activation_exact_threshold_and_reentry_resets_peak():
    r = run([(100,100,100,100), (100,102,99,102), (102,102,101,101.5),
             (101.5,101.5,101.5,101.5)],
            {0: Intent('long', profit_protection=ProfitProtection(2, 40)),
             2: Intent('long', profit_protection=ProfitProtection(2, 40))})
    assert r['trades'][0]['exit_price'] == pytest.approx(101.2)
    assert r['trades'][1]['protection_active'] is False
    assert r['trades'][1]['stop'] is None
    assert r['trades'][1]['profit_peak_pct'] == 0


def test_original_fixed_stop_is_kept_until_profit_protection_is_tighter():
    r = run([(100,100,100,100), (100,101,96,100), (100,100,94,95)],
            {0: Intent('long', stop_loss_pct=5, profit_protection=ProfitProtection(2, 40))})
    assert r['trades'][0]['exit_price'] == 95
    assert r['trades'][0]['exit_reason'] == 'stop_loss'


@pytest.mark.parametrize('protection', [ProfitProtection(0, 40), ProfitProtection(1, 100), ProfitProtection(True, 40), ProfitProtection(1, float('nan')), {}])
def test_invalid_protection_fails_before_entry(protection):
    with pytest.raises(ValueError, match='profit_protection'):
        run([(100,100,100,100)]*2, {0: Intent('long', profit_protection=protection)})


def test_new_strategy_disabled_protection_matches_current_baseline():
    root = Path(__file__).parents[1]
    path = root/'strategies/trend_cloud_profit_protection.py'
    assert inspect_strategy(path.read_bytes(), path.name).id == path.stem
    new, ns = load_strategy(path)
    old, os = load_strategy(root/'strategies/trend_cloud_experiments.py')
    bars = []
    for i in range(1300):
        price = 100+7*sin(i/17)+3*sin(i/2)
        bars.append(Bar(i*900000, price, price+1, price-1, price, 100))
    original = simulate(bars, old, validate_parameters(os, {'entry_filter': 'distance2', 'record_indicators': False}), warmup=650, step_ms=900000)
    candidate = simulate(bars, new, validate_parameters(ns, {'record_indicators': False}), warmup=650, step_ms=900000)
    assert len(original['trades']) > 5
    assert original['trades'] == candidate['trades']
    assert original['equity'] == candidate['equity']


def test_future_extrema_cannot_change_earlier_protection_or_fills():
    prefix = [(100,100,100,100), (100,105,99,104), (104,110,104,109)]
    actions = {0: Intent('long', profit_protection=ProfitProtection(2, 40))}
    first = run(prefix+[(109,115,100,110)], actions)
    changed = run(prefix+[(90,1000,1,500)], actions)
    assert first['levels'] == changed['levels']
    assert first['equity'][:-1] == changed['equity'][:-1]
    assert first['signals'] == changed['signals']
