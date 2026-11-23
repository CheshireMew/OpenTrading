from app.domain.cloud_entry_path_audit import barrier_path,complete_window,preentry_features
import pytest


def path(rows,side=1,exit_time=99,exit_phase='open'):
    return barrier_path(rows,100,side,2,1,exit_time,exit_phase,1)


def test_both_intrabar_barriers_are_ambiguous():
    r=path([[0,100,103,98,101,1]])
    assert r['order']=='same_bar_ambiguous' and r['category']=='bar_order_unknown'


def test_adverse_first_then_recovery_is_not_clean_opportunity():
    r=path([[0,100,100.5,98.5,99,1],[1,99,103,98,102,1]])
    assert r['order']=='adverse_first' and r['category']=='adverse_before_target'


def test_opening_target_has_known_priority_over_same_bar_downside():
    r=path([[0,100,101,99.5,100,1],[1,103,104,98,100,1]])
    assert r['order']=='target_first'
    assert r['first_target']['phase']=='open' and r['first_adverse']['phase']=='intrabar'


@pytest.mark.parametrize('side',[1,-1])
def test_target_after_actual_exit_is_distinguished_from_preexit(side):
    rows=[[0,100,101,99.5,100.5,1],[1,100.5,103,100.5,102,1]]
    if side==-1:rows=[[t,200-o,200-l,200-h,200-c,v] for t,o,h,l,c,v in rows]
    r=path(rows,side,0,'open')
    assert r['category']=='target_first_after_exit'


def test_same_exit_candle_does_not_invent_intrabar_order():
    r=path([[0,100,103,99.5,102,1]],exit_time=0,exit_phase='intrabar')
    assert r['category']=='target_first_same_time_ambiguous'


def test_gap_or_insufficient_future_is_not_counted_as_no_opportunity():
    rows=[[t,100,101,99,100,1] for t in (0,1,3,4)]
    assert complete_window(rows,[r[0] for r in rows],0,4,1)==(None,'gap')
    assert complete_window(rows,[r[0] for r in rows],3,4,1)==(None,'history_end')


def test_preentry_features_ignore_all_future_crossings_and_entry_fill():
    xs=[dict(timestamp=t,side=s,er=.2,atr_pct=.5) for t,s in [(0,'long'),(2,'short'),(3,'long')]]
    before=preentry_features(xs,3,100,1)
    xs.append(dict(timestamp=4,side='short',er=.01,atr_pct=10))
    assert preentry_features(xs,3,10000,1)==before
    assert before['prior16_direction_flips']==2 and not before['flips_good']
    assert before['er_good'] and before['stop_good']
