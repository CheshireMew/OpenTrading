from pathlib import Path
from math import sin
from types import SimpleNamespace
import pytest
from app.domain.local_backtest import Bar, Intent, ProfitProtection, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters, inspect_strategy

ROOT = Path(__file__).parents[1]
SOURCE = ROOT/'strategies/trend_cloud_parameters_v4.py'
STEP = 900000


def load(**p):
    m, s = load_strategy(SOURCE)
    return m, validate_parameters(s, {'record_indicators': False, **p})


def bar(i, p=100):
    return Bar(i*STEP, p, p+1, p-1, p, 1)


def test_defaults_exactly_reproduce_ema55_and_are_inspectable():
    data = [bar(i, 100+8*sin(i/17)) for i in range(2000)]
    m, p = load()
    old, s = load_strategy(ROOT/'strategies/trend_cloud_robustness_v1.py')
    a = simulate(data, m, p, warmup=650, step_ms=STEP)
    b = simulate(data, old, validate_parameters(s, {'center_length': 55, 'record_indicators': False}), warmup=650, step_ms=STEP)
    assert len(a['trades']) > 5
    assert a == b
    assert inspect_strategy(SOURCE.read_bytes(), SOURCE.name).id == SOURCE.stem


@pytest.mark.parametrize('side,d', [('long', 1), ('short', -1)])
def test_chase_distance_only_blocks_entries_and_never_opposite_exit(side, d):
    def decision(chase, position):
        m, p = load(chase_mult=chase)
        c = m.Calculation(p)
        for i in range(650):
            c.update(bar(i), decisions=False)
        return c.update(Bar(650*STEP, 100, 105, 95, 100+d*4, 1), position)
    assert decision(1.25, None) is None
    assert decision(0, None).action == side
    assert decision(2, None).action == side
    assert decision(1.25, {'side': 'short' if d == 1 else 'long'}).action == 'close'


@pytest.mark.parametrize('side,d', [('long', 1), ('short', -1)])
def test_width_stop_uses_only_signal_width_and_mirrors_sides(side, d):
    m, p = load(initial_stop_width=3)
    c = m.Calculation(p)
    for i in range(650):
        c.update(bar(i), decisions=False)
    r = c.update(Bar(650*STEP, 100, 104, 96, 100+2*d, 1))
    assert r.action == side
    assert r.stop_loss_pct == pytest.approx(100*3*c.width/(100+2*d))


@pytest.mark.parametrize('side,d', [('long', 1), ('short', -1)])
def test_initial_stop_is_anchored_to_actual_fill_and_live_on_entry_bar(side, d):
    def on_bar(ctx):
        return Intent(side, stop_loss_pct=1, profit_protection=ProfitProtection(2, 50)) if len(ctx.history) == 1 else None
    data = [bar(0), Bar(STEP, 110, 112, 108, 110, 1)]
    r = simulate(data, SimpleNamespace(on_bar=on_bar), {}, warmup=0, step_ms=STEP)
    t = r['trades'][0]
    assert t['entry_price'] == 110
    assert t['exit_reason'] == 'stop_loss' and t['exit_time'] == STEP
    assert t['exit_price'] == pytest.approx(110*(1-d*.01))


@pytest.mark.parametrize('side,d', [('long', 1), ('short', -1)])
def test_profit_protection_tightens_initial_stop_only_next_bar(side, d):
    def mirror(b):
        return b if d == 1 else Bar(b.timestamp, 200-b.open, 200-b.low, 200-b.high, 200-b.close, 1)
    def on_bar(ctx):
        return Intent(side, stop_loss_pct=1, profit_protection=ProfitProtection(2, 50)) if len(ctx.history) == 1 else None
    data = [bar(0), Bar(STEP, 100, 104, 99.5, 103, 1), Bar(2*STEP, 103, 103.5, 101, 102, 1)]
    r = simulate([mirror(b) for b in data], SimpleNamespace(on_bar=on_bar), {}, warmup=0, step_ms=STEP)
    t = r['trades'][0]
    assert t['exit_time'] == 2*STEP and t['exit_reason'] == 'profit_protection'
    assert t['return_pct'] == pytest.approx(2)


def test_selection_ranks_return_without_win_rate_gate():
    from scripts.cloud_parameter_study import rank, factor_winners, GROUPS
    rows = {'baseline': {'return_pct': 100, 'wins': 30, 'losses': 70}, 'highwin': {'return_pct': 50, 'wins': 70, 'losses': 30}}
    assert rank(rows) == ['baseline', 'highwin']
    variants = {'baseline': {'group': 'baseline'}, 'highwin': {'group': 'center'}}
    assert factor_winners(variants, rows) == {g: 'baseline' for g in GROUPS}
