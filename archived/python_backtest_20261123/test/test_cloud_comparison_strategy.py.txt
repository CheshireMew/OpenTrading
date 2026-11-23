from pathlib import Path
import pytest
from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters


@pytest.mark.parametrize('variant,parameters', [
    ('ema31_atr', {'mode': 'cross', 'source': 'hlc3', 'ema_length': 31, 'cloud_mult': .45, 'trigger_mult': .99}),
    ('original_05', {'mode': 'original', 'cloud_mult': .5}),
    ('original_15', {'mode': 'original', 'cloud_mult': 1.5}),
])
def test_study_preserves_previous_candidate_and_original_formulas(variant, parameters):
    root = Path(__file__).parents[1]
    old, old_spec = load_strategy(root/'strategies/adaptive_cloud.py')
    new, new_spec = load_strategy(root/'strategies/trend_cloud_comparison.py')
    bars = [Bar(i*900000, 100+i%29, 106+i%29, 98+i%29, 103+i%29, 100+i%113) for i in range(850)]
    before = simulate(bars, old, validate_parameters(old_spec, parameters), warmup=650, step_ms=900000)
    after = simulate(bars, new, validate_parameters(new_spec, {'variant': variant}), warmup=650, step_ms=900000)
    assert [(s['timestamp'], s['action']) for s in before['signals']] == [(s['timestamp'], s['action']) for s in after['signals']]
    assert [v['cloud'] for v in before['indicators']] == [v['cloud'] for v in after['indicators']]
