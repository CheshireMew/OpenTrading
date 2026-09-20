from itertools import product
from scripts.cloud_joint_study import combinations, AXES, token, variant_key, rank, interactions, gap_sensitivity


def test_every_declared_combination_once_and_named_example_present():
    variants = combinations()
    assert len(variants) == len({token(x['parameters']) for x in variants.values()}) == 128
    expected = set(product(*AXES.values()))
    assert {tuple(x['parameters'][k] for k in AXES) for x in variants.values()} == expected
    assert 'c65_w40_t0p8_d2_a3_g40_s0' in variants
    assert 'c65_w40_t0p8_d2_a3_g40_s1' in variants


def test_return_ranking_is_within_one_period_and_does_not_gate_win_rate():
    r = {'a': {'selection': {'return_pct': 80}, 'full': {'return_pct': 500}},
         'b': {'selection': {'return_pct': 90}, 'full': {'return_pct': 100}}}
    assert rank(r, 'selection') == ['b', 'a']
    assert rank(r, 'full') == ['a', 'b']


def test_interaction_pairs_change_exactly_one_factor():
    v = combinations()
    r = {k: {'full': {'return_pct': x['parameters']['center_length']}} for k, x in v.items()}
    x = interactions({'variants': v, 'axes': AXES}, r, 'full')
    assert x['center_length']['better'] == x['center_length']['comparisons'] == 64
    assert x['center_length']['median_change_pct_points'] == 10
    assert all(x[f]['better'] == x[f]['worse'] == 0 for f in AXES if f != 'center_length')


def test_gap_sensitivity_catches_carried_and_delayed_entry_and_is_accounting_only():
    trades = [dict(trade_id=1, entry_time=0, exit_time=30, return_pct=10, profit=10),
              dict(trade_id=2, entry_time=30, exit_time=40, return_pct=-5, profit=-5),
              dict(trade_id=3, entry_time=50, exit_time=60, return_pct=2, profit=2)]
    x = gap_sensitivity(trades, [dict(start=20, end=30)])
    assert x['affected_trade_ids'] == [1, 2]
    assert abs(x['return_with_affected_set_to_zero_pct']-2) < 1e-8
