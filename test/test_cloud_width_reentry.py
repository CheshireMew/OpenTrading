from pathlib import Path
from types import SimpleNamespace
from math import sin
import pytest
from app.domain.local_backtest import Bar, Intent, simulate
from app.services.local_backtest_strategies import load_strategy, validate_parameters

ROOT = Path(__file__).parents[1]
STEP = 900000


def load(**overrides):
    m, spec = load_strategy(ROOT/'strategies/trend_cloud_width_reentry_v1.py')
    return m, validate_parameters(spec, {'record_indicators': False, **overrides})


def candle(i, close=100, high=101, low=99):
    return Bar(i*STEP, close, high, low, close, 1)


def primed(**p):
    m, values = load(**p)
    c = m.Calculation(values)
    for i in range(650):
        c.update(candle(i), decisions=False)
    return c


def test_context_reports_same_bar_stop_at_close_and_is_immutable():
    seen = []
    def strategy(ctx):
        seen.append(ctx.last_exit)
        if len(ctx.history) == 1:
            return Intent('long', stop_loss_pct=1)
        with pytest.raises(TypeError):
            ctx.last_exit['side'] = 'short'
    simulate([candle(0), candle(1, low=98), candle(2)], SimpleNamespace(on_bar=strategy), {}, warmup=0)
    assert seen[0] is None
    assert seen[1]['exit_time'] == STEP and seen[1]['exit_reason'] == 'stop_loss'
    assert seen[1] == seen[2]


def test_original_mode_exact_execution_parity():
    bars = [candle(i, 100+8*sin(i/17), 101+8*sin(i/17), 99+8*sin(i/17)) for i in range(3000)]
    new, p = load()
    old, spec = load_strategy(ROOT/'strategies/trend_cloud_parameters_v4.py')
    old_p = validate_parameters(spec, dict(trigger_mult=.4, initial_stop_pct=1, record_indicators=False))
    a = simulate(bars, new, p, warmup=650, step_ms=STEP)
    b = simulate(bars, old, old_p, warmup=650, step_ms=STEP)
    assert len(a['trades']) > 20
    assert a == b


def test_median_excludes_current_and_requires_full_previous_window():
    m, _ = load()
    r = m.PreviousMedian(4)
    assert [r.relative_then_append(x) for x in (1, 1, 1, 1)] == [1]*4
    assert r.relative_then_append(10) == 10
    assert r.relative_then_append(1) == 1


def test_mode_switch_alone_does_not_generate_a_cross():
    c = primed(entry_mode=2)
    c.base, c.width, c.pc, c.narrow = 100, 2, 102, True
    assert c.update(candle(650, 102, 103, 101)) is None
    c.narrow = False  # The price was already above the inner line on both closes.
    assert c.update(candle(651, 102, 103, 101)) is None


@pytest.mark.parametrize('d,side', [(1, 'long'), (-1, 'short')])
def test_outer_mode_does_not_use_conflicting_chase_cap(d, side):
    c = primed(entry_mode=1)
    decision = c.update(candle(650, 100+d*6, 106, 94))
    assert decision.action == side


def test_dynamic_stop_uses_completed_signal_width_and_is_clamped():
    c = primed(dynamic_stop=True)
    r = c.update(candle(650, 105, 140, 60))
    assert r.action == 'long' and r.stop_loss_pct == 2
    c = primed(dynamic_stop=True, reference_bars=2, width_length=2)
    c.width = .05
    r = c.update(candle(650, 100.04, 100.05, 99.95))
    assert r.action == 'long' and r.stop_loss_pct == .5


@pytest.mark.parametrize('d,side', [(1, 'long'), (-1, 'short')])
def test_retry_once_even_if_reentry_stops_again_and_no_repeated_holding_signal(d, side):
    c = primed(stop_reentry=True)
    c.last_cross_side = side
    stop = dict(trade_id=1, side=side, exit_reason='stop_loss')
    r = c.update(candle(650, 100+d*6, 106, 94), last_exit=stop)
    assert r.action == side and r.reason == '初始止损后补一次'
    stop2 = dict(stop, trade_id=2)
    assert c.update(candle(651, 100+d*6, 106, 94), last_exit=stop2) is None
    assert c.update(candle(652, 100+d*6, 106, 94), last_exit=stop2) is None
    assert c.used[side]
    # A new same-side inner crossing during an existing position is silent.
    c.pc = 100
    c.base, c.width = 100, 2
    assert c.update(candle(653, 100+d, 101, 99), position={'side': side}) is None


def test_profit_protection_exit_is_not_a_retry_and_opposite_cross_resets_quota():
    c = primed(stop_reentry=True)
    r = c.update(candle(650, 106, 106, 94), last_exit=dict(trade_id=1, side='long', exit_reason='profit_protection'))
    assert r is None  # beyond chase cap, and not an initial-stop retry
    c.used['long'] = True
    c.update(candle(651, 95, 106, 94))
    assert not c.used['long'] and c.last_cross_side == 'short'


def test_prefix_causality_for_bb_regime_and_stop_reentry():
    data = [candle(i, 100+6*sin(i/11), 101+6*sin(i/11), 99+6*sin(i/11)) for i in range(900)]
    def observations(rows):
        m, p = load(entry_mode=3, dynamic_stop=True, stop_reentry=True, record_indicators=True)
        return simulate(rows, m, p, warmup=650, step_ms=STEP)['indicators']
    assert observations(data[:800]) == observations(data)[:150]


def test_end_to_end_entry_stop_reentry_stop_never_loops():
    m, p = load(stop_reentry=True)
    data = [candle(i) for i in range(650)] + [
        Bar(650*STEP, 100, 102, 100, 101, 1),
        Bar(651*STEP, 101, 106, 98, 106, 1),
        Bar(652*STEP, 106, 107, 104, 107, 1),
        Bar(653*STEP, 107, 108, 106, 108, 1),
        Bar(654*STEP, 108, 109, 107, 109, 1),
    ]
    r = simulate(data, m, p, warmup=650, step_ms=STEP)
    assert len(r['trades']) == 2
    assert all(t['exit_reason'] == 'stop_loss' for t in r['trades'])
    entries = [f for f in r['fills'] if f['action'] == 'long']
    assert [f['timestamp'] for f in entries] == [651*STEP, 652*STEP]
    assert entries[1]['reason'] == '初始止损后补一次'
