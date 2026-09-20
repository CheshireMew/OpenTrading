from scripts.alt_cloud_parameter_study import variants, AXES, ETH_PARAMETERS, BTC_PARAMETERS, key, allowed, choose


def test_small_joint_grid_retains_both_transfer_controls():
    grid=variants()
    assert len(grid)==64
    assert grid[key(ETH_PARAMETERS)]['parameters']==ETH_PARAMETERS
    assert grid[key(BTC_PARAMETERS)]['parameters']==BTC_PARAMETERS
    assert all(v['parameters']['giveback_pct']==50 for v in grid.values())
    assert all(v['parameters']['trigger_mult']<v['parameters']['chase_mult'] for v in grid.values())


def test_hindsight_winners_do_not_replace_pre2024_choice():
    rows={'one':{'train':{'return_pct':20},'final':{'return_pct':-90},'full':{'return_pct':0}},
          'two':{'train':{'return_pct':10},'final':{'return_pct':900},'full':{'return_pct':1000}}}
    assert choose(rows,rows)==['one','two']
    assert choose(rows,rows,'full')==['two','one']


def test_only_original_transfer_controls_may_see_future_before_selection_lock():
    p={'assets':{'paxg':{}},'variants':{'old':{},'new':{}},'transfer':{'ETH':'old'}}
    assert allowed('transfer','final',p,'paxg','old')
    assert not allowed('transfer','full',p,'paxg','new')
    assert not allowed('train','final',p,'paxg','new')
    assert not allowed('evaluate','full',p,'paxg','new')
    assert allowed('evaluate','full',p,'paxg','new',{'assets':{'paxg':{'selected':'old'}}})
