from math import sin
from pathlib import Path

import pytest

from app.domain.backtest_diagnostics import diagnose
from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters, inspect_strategy

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize('direction', [1, -1])
def test_excursions_respect_exit_open_and_entry_information(direction):
    bars = [Bar(i*900000, 100, 101, 99, 100, 100) for i in range(45)]
    if direction == 1:
        bars[41] = Bar(41*900000, 100, 110, 96, 108, 100)
        bars[42] = Bar(42*900000, 108, 112, 97, 99, 100)
    else:
        bars[41] = Bar(41*900000, 100, 104, 90, 92, 100)
        bars[42] = Bar(42*900000, 92, 103, 88, 101, 100)
    exit_price = 100-2*direction
    bars[43] = Bar(43*900000, exit_price, 200, 1, 150, 100)
    t = dict(entry_time=bars[41].timestamp, exit_time=bars[43].timestamp, entry_price=100,
             exit_price=exit_price, exit_phase='open', direction=direction,
             side='long' if direction == 1 else 'short', profit=-200, return_pct=-2,
             duration_minutes=30)
    detail = diagnose(bars, {'trades': [t]})
    before = detail['trades'][0]
    assert before['mfe_pct'] == 12
    assert before['mae_pct'] == 4
    assert before['max_close_profit_pct'] == 8
    assert before['giveback_pct'] == 14
    assert detail['report']['losses_previously_up']['1.0']['intrabar_count'] == 1
    bars[43] = Bar(43*900000, exit_price, 1000, .1, 500, 100)
    assert diagnose(bars, {'trades': [t]}) == detail
    t['exit_phase'] = 'intrabar'
    with pytest.raises(ValueError, match='pre-exit extrema'):
        diagnose(bars, {'trades': [t]})


@pytest.mark.parametrize('variant,parameters', [
    ('high_low_ema', {'source': 'hl2', 'width': 'range_ema', 'width_period': 16}),
    ('ema31_atr', {'source': 'hlc3', 'width': 'atr', 'width_period': 14}),
    ('ema31_range', {'source': 'hlc3', 'width': 'range', 'width_period': 14}),
    ('ema31_cross', {'source': 'hlc3', 'width': 'none', 'width_period': 14}),
])
def test_experiment_baselines_preserve_original_transactions(variant, parameters):
    bars = []
    for i in range(1200):
        price = 100+8*sin(i/19)+3*sin(i/3)
        bars.append(Bar(i*900000, price-.1, price+1, price-1, price, 100))
    original, spec = load_strategy(ROOT/'strategies/trend_cloud_comparison.py')
    experiment, es = load_strategy(ROOT/'strategies/trend_cloud_experiments.py')
    before = simulate(bars, original, validate_parameters(spec, {'variant': variant, 'record_indicators': False}), warmup=650, step_ms=900000)
    after = simulate(bars, experiment, validate_parameters(es, {**parameters, 'record_indicators': False}), warmup=650, step_ms=900000)
    assert len(before['trades']) > 5
    assert after['trades'] == before['trades']
    assert after['equity'] == before['equity']


def test_filter_rejects_chase_but_still_closes_opposite_position():
    path = ROOT/'strategies/trend_cloud_experiments.py'
    assert inspect_strategy(path.read_bytes(), path.name).id == 'trend_cloud_experiments'
    module, spec = load_strategy(path)
    calc = module.Calculation(validate_parameters(spec, {'entry_filter': 'distance2'}))
    for i in range(50):
        calc.update(Bar(i*900000, 100, 101, 99, 100, 100))
    result = calc.update(Bar(50*900000, 100, 121, 100, 120, 100), {'side': 'short'})
    assert result.checks['原做多信号']
    assert not result.checks['允许入场']
    assert result.intent.action == 'close'


def test_confirmation_waits_for_second_close_and_rejects_failed_breakout():
    module, spec = load_strategy(ROOT/'strategies/trend_cloud_experiments.py')
    for next_close, expected in ((120, 'long'), (101, None)):
        calc = module.Calculation(validate_parameters(spec, {'confirmation': 2}))
        for i in range(50):
            calc.update(Bar(i*900000, 100, 101, 99, 100, 100))
        first = calc.update(Bar(50*900000, 100, 121, 100, 120, 100))
        assert first.intent is None
        second = calc.update(Bar(51*900000, 120, 121, 100, next_close, 100))
        assert (second.intent.action if second.intent else None) == expected
