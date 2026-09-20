import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.contracts.parameter_sweep import ParameterRange, ParameterSweepCommand, ParameterSweepView
from app.infra.research_files import read_json, atomic_json, file_hash
from app.services.parameter_sweep_service import ParameterSweepService
from app.services.market.history_range_coordinator import OhlcvRangeResult
from scripts.local_backtest_worker import execute
from test.test_local_backtest_service import setup_service


@pytest.fixture
def sweep(setup_service, tmp_path):
    backtest, command, market = setup_service
    path = tmp_path/'test_strategy.py'
    path.write_text('''from app.domain.local_backtest import Intent
STRATEGY=dict(id='test_strategy',name='test',description='test',api_version='1',warmup_bars=1,parameters={
 'stop':{'type':'float','default':1,'min':.1,'max':10}, 'length':{'type':'int','default':2,'min':1,'max':10}})
def on_bar(c):
 return Intent('long', c.parameters['stop'], 20) if len(c.history)==c.parameters['length'] else None
''', encoding='utf8')
    return ParameterSweepService(backtest,tmp_path/'studies'), dict(title='参数比较测试',base=command.model_dump(mode='json'),axes={'parameters.stop':{'start':.5,'end':1,'step':.5},'parameters.length':[2,3,2]}), market


def finish(s, market):
    while rid:=s.backtests.repository.claim():
        execute(s.backtests,rid,market)


def test_grid_decimal_limits_and_invalid_axis_before_submission(sweep):
    s,p,_=sweep
    assert ParameterRange(start=.1,end=.3,step=.1).values()==[.1,.2,.3]
    assert ParameterRange(start=1,end=2,step=.7).values()==[1,1.7]
    preview=s.preview(p)
    assert (preview['count'],preview['new_runs'])==(4,4)
    assert s.backtests.repository.list()['total']==0
    for axes in ({'bogus':[1]}, {'parameters.unknown':[1]}, {'parameters.stop':[]}, {'parameters.length':[1.5]}, {'parameters.stop':[11]}, {'parameters.stop':dict(start=1,end=0,step=1)}, {'parameters.stop':dict(start=1,end=5,step=0)}):
        with pytest.raises(ValueError):s.create({**p,'axes':axes})
    with pytest.raises(ValueError,match='上限'):s.preview({**p,'max_runs':3})
    assert s.backtests.repository.list()['total']==0


def test_position_execution_and_protection_axes_are_preserved_in_config_and_export(sweep):
    import csv
    import io
    s,p,_=sweep
    p['axes']={'position_pct':[100,50,25], 'execution_timeframe':['5m','1m'], 'intrabar_profit_protection':[False,True]}
    preview=s.preview(p)
    assert preview['count']==12
    view=s.create(p)
    assert view['total']==12
    configs=[item['config'] for item in view['items']]
    assert {c['position_pct'] for c in configs}=={100,50,25}
    assert {(c['execution_timeframe'],c['intrabar_profit_protection']) for c in configs}=={('5m',False),('5m',True),('1m',False),('1m',True)}
    exported=list(csv.DictReader(io.StringIO(s.export(view['id'])['content'].lstrip('\ufeff'))))
    assert {r['position_pct'] for r in exported}=={'100.0','50.0','25.0'}
    assert {r['execution_timeframe'] for r in exported}=={'5m','1m'}
    assert {r['intrabar_profit_protection'] for r in exported}=={'False','True'}


def test_no_fine_timeframe_axis_is_explicit_and_incompatible_protection_rejected(sweep):
    s,p,_=sweep
    p['axes']={'execution_timeframe':[None,'5m']}
    v=s.create(p)
    assert v['total']==2
    assert {i['config'].get('execution_timeframe') for i in v['items']}=={None,'5m'}
    assert s.backtests.repository.list()['total']==2
    with pytest.raises(ValueError,match='必须指定细周期'):
        s.preview({**p,'axes':{'execution_timeframe':[None,'5m'],'intrabar_profit_protection':[False,True]}})
    assert s.backtests.repository.list()['total']==2


def test_batch_matches_direct_engine_reuses_one_dataset_and_keeps_records(sweep):
    s,p,market=sweep
    v=s.create(p);identifier=v['id'];frozen=(s.studies.folder(identifier)/'plan.json').read_bytes()
    assert ParameterSweepView.model_validate(v).total==4
    calls=[]
    def load(*a):calls.append(a);return market.load_ohlcv_range(*a)
    # Exercise the same Windows file lock used by independent worker processes.
    first,second=s.backtests.repository.claim(),s.backtests.repository.claim()
    with ThreadPoolExecutor(2) as pool:
        jobs=[pool.submit(execute,s.backtests,rid,SimpleNamespace(load_ohlcv_range=load)) for rid in (first,second)]
        for job in jobs:job.result()
    finish(s,SimpleNamespace(load_ohlcv_range=load))
    assert len(calls)==1
    v=s.get(identifier);assert v['status']=='completed' and v['progress']==1
    assert len({s.backtests.repository.get(i['run_id'])['metadata']['data_hash'] for i in v['items']})==1
    returns=[i['report']['return_pct'] for i in v['items']];assert returns==sorted(returns,reverse=True)
    assert s.get(identifier,offset=2,limit=1)['items'][0]==v['items'][2]
    assert s.get(identifier,minimum_trades=100)['filtered_total']==0
    before=s.backtests.repository.list()['total'];s.resume(identifier);assert s.backtests.repository.list()['total']==before
    assert (s.studies.folder(identifier)/'plan.json').read_bytes()==frozen
    # One corresponding single run gives identical fills/trades/equity, not just totals.
    case=s.studies.plan(identifier)['cases'][0]
    direct=s.backtests.create(ParameterSweepCommand.model_validate({**p,'base':case['config']}).base)
    finish(s,market)
    batch_run=next(i['run_id'] for i in v['items'] if i['case']==case['id'])
    assert s.backtests.result(direct['id'])==s.backtests.result(batch_run)
    effects=s.effects(identifier)['effects'];assert all(e['pairs'] for e in effects)
    csv=s.export(identifier);assert csv['content'].startswith('\ufeff') and csv['content'].count('\n')==5
    assert list((s.studies.folder(identifier)/'rankings').glob('*.json'))
    copied=s.create({**p,'parent':identifier,'title':'新版'})
    assert copied['id']!=identifier and s.get(identifier)['status']=='completed'


def test_cancel_resume_preserves_completed_and_failed_attempts(sweep):
    s,p,market=sweep;v=s.create(p);identifier=v['id']
    rid=s.backtests.repository.claim();execute(s.backtests,rid,market)
    old_ids={i['case']:i['run_id'] for i in s.get(identifier)['items']}
    cancelled=s.cancel(identifier);assert cancelled['counts']=={'completed':1,'cancelled':3}
    resumed=s.resume(identifier);assert resumed['counts']=={'completed':1,'queued':3}
    assert next(i for i in resumed['items'] if i['status']=='completed')['run_id']==rid
    for i in resumed['items']:
        if i['status']=='queued':
            assert i['run_id']!=old_ids[i['case']]
            assert s.backtests.repository.get(old_ids[i['case']])['status']=='cancelled'
    finish(s,SimpleNamespace(load_ohlcv_range=lambda *a:pytest.fail('恢复应复用冻结行情')))
    assert s.get(identifier)['status']=='completed'


def test_source_seed_uses_fine_data_and_reuses_exact_baseline(sweep):
    s,p,market=sweep
    p['base'].update(execution_timeframe='5m',intrabar_profit_protection=True)
    command=ParameterSweepCommand.model_validate(p).base
    t=int(command.start.timestamp()*1000)
    fine=[[t+i*300000,100,101,99,100,1] for i in range(48)]
    baseline=s.backtests.create(command)
    finish(s,SimpleNamespace(load_ohlcv_range=lambda symbol,tf,*a:OhlcvRangeResult(fine,[]) if tf=='5m' else market.load_ohlcv_range()))
    p['source_run']=baseline['id'];p['axes']={'parameters.stop':[1,2]}
    assert s.preview(p)['reused_runs']==1
    v=s.create(p)
    finish(s,SimpleNamespace(load_ohlcv_range=lambda *a:pytest.fail('种子行情不应下载')))
    v=s.get(v['id']);assert v['status']=='completed'
    hashes={s.backtests.repository.get(i['run_id'])['metadata']['execution_data_hash'] for i in v['items']}
    assert len(hashes)==1
    assert s.effects(v['id'])['effects'][0]['pairs'][0]['paired_comparisons']==1
    # Changed strategy code must not reuse a historic result as if it were current.
    path=s.backtests.root.parent/'test_strategy.py'
    path.write_text(path.read_text(encoding='utf8')+'\n# new version\n',encoding='utf8')
    assert s.preview(p)['reused_runs']==0


def test_failed_submission_has_visible_error_and_can_recover(sweep, monkeypatch):
    from app.services.parameter_sweep_service import SweepBacktests
    s,p,_=sweep;original=SweepBacktests._create
    def fail(*a,**k):raise ValueError('模拟提交中断')
    monkeypatch.setattr(SweepBacktests,'_create',fail)
    v=s.create(p);assert v['status']=='attention'
    assert all(i['error']=='模拟提交中断' for i in v['items'])
    monkeypatch.setattr(SweepBacktests,'_create',original)
    assert s.resume(v['id'])['counts']=={'queued':4}
    assert not any(i['error'] for i in s.get(v['id'])['items'])


def test_api_and_cli_use_same_saved_batches(sweep, api_harness, monkeypatch):
    from app.routers.local_backtests import service as dependency
    from scripts.research_cli import build_parser, execute as cli_execute
    from config import settings
    s,p,market=sweep
    monkeypatch.setattr(settings,'RUNTIME_ROOT_DIR',s.studies.root.parent)
    # The production default folder differs from the fixture's explicit studies folder.
    s.studies.root=s.studies.root.parent/'research_studies'
    client=api_harness['client'];client.app.dependency_overrides[dependency]=lambda:s.backtests
    try:
        response=client.post('/api/v1/parameter-sweeps/preview',json=p);assert response.status_code==200,response.text
        response=client.post('/api/v1/parameter-sweeps',json=p);assert response.status_code==200,response.text
        identifier=response.json()['id'];finish(s,market)
        assert client.get(f'/api/v1/parameter-sweeps/{identifier}').json()['status']=='completed'
        assert client.get(f'/api/v1/parameter-sweeps/{identifier}/effects').status_code==200
        assert client.get(f'/api/v1/parameter-sweeps/{identifier}/export').json()['filename'].endswith('.csv')
        assert client.get('/api/v1/parameter-sweeps').json()['total']==1
        monkeypatch.setattr('scripts.parameter_sweep_cli.build_database_runtime',lambda settings:s.backtests.repository.database)
        monkeypatch.setattr('scripts.parameter_sweep_cli.LocalBacktestService',lambda db:s.backtests)
        got=asyncio.run(cli_execute(build_parser().parse_args(['sweep','status',identifier,'--limit','2'])))
        assert got['status']=='completed' and len(got['items'])==2
    finally:client.app.dependency_overrides.pop(dependency,None)


def test_two_worker_runtime_shuts_down_both_processes(sweep):
    from app.services.local_backtest_runtime import LocalBacktestRuntime
    s,p,market=sweep
    # Real subprocesses use the conventional local_backtests directory.
    s.backtests.root=s.backtests.root.parent/'local_backtests'
    path=s.backtests.root.parent/'test_strategy.py'
    path.write_text(path.read_text(encoding='utf8')+'\nimport time\ndef on_bar(c):\n time.sleep(20)\n',encoding='utf8')
    p['axes']={'parameters.stop':[1,2]};v=s.create(p)
    for i in v['items']:
        folder=s.backtests.directory(i['run_id']);atomic_json(folder/'data.json',market.load_ohlcv_range().rows)
        meta=read_json(folder/'metadata.json');meta['data_hash']=file_hash(folder/'data.json');atomic_json(folder/'metadata.json',meta)
    runtime=LocalBacktestRuntime(s.backtests.repository.database);runtime.service=s.backtests
    async def scenario():
        await runtime.start()
        try:
            async with asyncio.timeout(20):
                while s.get(v['id'])['counts'].get('running')!=2:await asyncio.sleep(.1)
            children=list(runtime.processes.values());assert len(children)==2
            await runtime.shutdown()
            assert all(child.poll() is not None for child in children)
            assert s.get(v['id'])['counts']=={'interrupted':2}
        finally:await runtime.shutdown()
    asyncio.run(scenario())


def test_chunked_history_recovers_completed_chunks_and_rejects_timeout_prefix(tmp_path):
    from app.services.backtest_history_loader import load_history
    step=300000;rows=[[i*step,100,101,99,100,1] for i in range(10)]
    calls=[]
    def fetch(symbol,tf,a,b):
        begin=int(a.timestamp()*1000);end=int(b.timestamp()*1000)+1;calls.append(begin)
        part=[r for r in rows if begin<=r[0]<end]
        return OhlcvRangeResult(part[:1] if begin==4*step else part,[])
    with pytest.raises(ValueError,match='完整边界'):
        load_history(SimpleNamespace(load_ohlcv_range=fetch),'BNB/USDT','5m',0,10*step,tmp_path,lambda _:None,chunk_bars=4)
    assert len(list((tmp_path/'5m').glob('*.json')))==1
    calls.clear()
    def resumed(symbol,tf,a,b):
        begin=int(a.timestamp()*1000);end=int(b.timestamp()*1000)+1;calls.append(begin)
        return OhlcvRangeResult([r for r in rows if begin<=r[0]<end],[])
    assert load_history(SimpleNamespace(load_ohlcv_range=resumed),'BNB/USDT','5m',0,10*step,tmp_path,lambda _:None,chunk_bars=4)==rows
    assert calls==[4*step,8*step]


def test_resume_after_signal_data_saved_before_fine_data(sweep):
    s,p,market=sweep;p['base'].update(execution_timeframe='5m',intrabar_profit_protection=True)
    p['axes']={};v=s.create(p);rid=s.backtests.repository.claim()
    def broken(symbol,tf,*a):
        if tf=='5m':raise ValueError('模拟细行情暂不可用')
        return market.load_ohlcv_range()
    with pytest.raises(ValueError,match='暂不可用'):execute(s.backtests,rid,SimpleNamespace(load_ohlcv_range=broken))
    s.backtests.repository.patch(rid,status='failed',error='模拟细行情暂不可用')
    assert read_json(s.backtests.directory(rid)/'metadata.json')['data_hash']
    s.resume(v['id'])
    start=int(ParameterSweepCommand.model_validate(p).base.start.timestamp()*1000)
    fine=[[start+i*300000,100,101,99,100,1] for i in range(48)]
    def fetched(symbol,tf,*a):
        assert tf=='5m','原信号数据已经保存，不应重新下载'
        return OhlcvRangeResult(fine,[])
    finish(s,SimpleNamespace(load_ohlcv_range=fetched))
    assert s.get(v['id'])['status']=='completed'
