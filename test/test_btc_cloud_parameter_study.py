from collections import Counter
from itertools import combinations
from scripts.btc_cloud_parameter_study import AXES, BASE, balanced_design, neighbors, key, allowed_task, choose_validation


def test_balanced_joint_design_covers_all_pairs_without_duplicate_configurations():
    rows=balanced_design()
    assert len(rows)==len({key(p) for p in rows})==243
    for field,levels in AXES.items():
        assert Counter(p[field] for p in rows)=={v:81 for v in levels}
    for a,b in combinations(AXES,2):
        counts=Counter((p[a],p[b]) for p in rows)
        assert len(counts)==9 and set(counts.values())=={27}


def test_neighborhood_changes_one_axis_and_retains_execution_parameters():
    for p in [BASE]+balanced_design():
        near=neighbors(p)
        assert len(near)==14
        for n in near:
            assert sum(n[f]!=p[f] for f in AXES)==1
            assert n['initial_stop_width']==0 and n['record_indicators'] is False
            assert n['chase_mult']>n['trigger_mult']


def test_final_requires_lock_and_membership_and_early_stages_reject_future():
    for stage in ('coarse','expansion','validation'):
        assert not allowed_task(stage,'final','a')
        assert not allowed_task(stage,'full','a')
    assert not allowed_task('final','final','a')
    assert not allowed_task('final','final','b',{'evaluation_keys':['a']})
    assert allowed_task('final','final','a',{'evaluation_keys':['a']})


def test_selection_ignores_final_return_and_neighbors_cannot_win():
    r={'a':{'validation':{'return_pct':10},'final':{'return_pct':-99}},
       'b':{'validation':{'return_pct':5},'final':{'return_pct':10000}},
       'neighbor':{'validation':{'return_pct':99999}}}
    assert choose_validation(r,['a','b'])=='a'
