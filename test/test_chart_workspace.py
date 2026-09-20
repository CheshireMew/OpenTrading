import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.contracts.chart_workspace import WorkspaceWrite, ChartSymbol, ChartBar, ChartBars, PineRunRequest
from app.services.chart_workspace_store import ChartWorkspaceStore, WorkspaceConflict, ROOT
from app.services.chart_workspace_market import close_boundary, ChartWorkspaceMarket
from app.services.chart_workspace_runs import ChartPineRuns
from app.main import create_app


def test_workspace_revisions_conflict_and_readonly(tmp_path):
    store=ChartWorkspaceStore(tmp_path)
    first=store.put('scripts','s',WorkspaceWrite(name='指标',data={'source':'first'}))
    second=store.put('scripts','s',WorkspaceWrite(name='指标',data={'source':'second'},expected_version=first.version))
    assert store.get('scripts','s',1).data['source']=='first'
    assert ChartWorkspaceStore(tmp_path).get('scripts','s').version==second.version
    with pytest.raises(WorkspaceConflict):
        store.put('scripts','s',WorkspaceWrite(name='指标',data={}))
    store.put('scripts','original',WorkspaceWrite(name='原版',data={}),readonly=True)
    with pytest.raises(WorkspaceConflict):
        store.archive('scripts','original')
    store.archive('scripts','s')
    assert [d.id for d in store.list('scripts')]==['original']
    assert store.get('scripts','s',1).data['source']=='first'


def test_market_identity_and_month_boundary():
    from datetime import datetime,timezone
    start=int(datetime(2024,2,1,tzinfo=timezone.utc).timestamp()*1000)
    end=int(datetime(2024,3,1,tzinfo=timezone.utc).timestamp()*1000)
    assert close_boundary(start,'1M')==end
    assert close_boundary(start,'1m')==start+60000


def test_retired_order_route_and_new_contracts():
    schema=create_app('api').openapi()
    assert '/api/v1/trade-setup' not in schema['paths']
    assert '/api/v1/chart-workspace/pine-runs' in schema['paths']
    assert not hasattr(__import__('app.services.market.insight_app_service',fromlist=['MarketInsightAppService']).MarketInsightAppService,'get_trade_setup')


@pytest.mark.asyncio
async def test_feed_shares_subscription_and_releases():
    market=ChartWorkspaceMarket(None,None)
    async def pump(*args):
        await asyncio.Event().wait()
    market._pump=pump
    a,b=asyncio.Queue(),asyncio.Queue()
    market.subscribe('binance:spot:BTCUSDT','1m',a)
    market.subscribe('binance:spot:BTCUSDT','1m',b)
    market.subscribe('binance:usdm:BTCUSDT','1m',b)
    assert len(market.channels)==2
    market.unsubscribe('binance:spot:BTCUSDT','1m',a)
    assert len(market.channels)==2
    market.unsubscribe('binance:spot:BTCUSDT','1m',b)
    assert len(market.channels)==1
    await market.close()


@pytest.mark.asyncio
async def test_usdm_stream_waits_for_data_and_heals_after_silence(monkeypatch):
    import app.services.chart_workspace_market as module
    market = ChartWorkspaceMarket(None, None)
    symbol = ChartSymbol(id='binance:usdm:BTCUSDT', symbol='BTCUSDT', name='BTC/USDT',
                         exchange='binance', market='usdm', currency='USDT', timeframes=['1m'])
    queue = asyncio.Queue()
    starts, urls, timeouts = [], [], []
    connections = 0

    async def resolve(_):
        return symbol

    async def bars(*args, **kwargs):
        starts.append(kwargs.get('start'))
        return ChartBars(symbol=symbol, timeframe='1m', bars=[], source='test')

    class Stream:
        calls = 0

        async def __aenter__(self):
            nonlocal connections
            connections += 1
            if connections == 2:
                raise asyncio.CancelledError()
            assert market.channel_status[(symbol.id, '1m')]['status'] == 'connecting'
            return self

        async def __aexit__(self, *args):
            pass

        async def recv(self):
            self.calls += 1
            if self.calls == 2:
                raise TimeoutError('No native kline received')
            return json.dumps({'k': {'t': 60000, 'T': 119999, 'o': '100', 'h': '102',
                                     'l': '99', 'c': '101', 'v': '5', 'x': False}})

    def connect(url, **kwargs):
        urls.append(url)
        return Stream()

    async def wait_for(task, timeout):
        timeouts.append(timeout)
        return await task

    async def sleep(_):
        pass

    monkeypatch.setattr(market, 'resolve', resolve)
    monkeypatch.setattr(market, 'bars', bars)
    monkeypatch.setattr(module.websockets, 'connect', connect)
    monkeypatch.setattr(module.asyncio, 'wait_for', wait_for)
    monkeypatch.setattr(module.asyncio, 'sleep', sleep)
    try:
        with pytest.raises(asyncio.CancelledError):
            await market._pump(symbol.id, '1m', {queue})
        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())
        assert urls == ['wss://fstream.binance.com/market/ws/btcusdt@kline_1m'] * 2
        assert timeouts == [30, 30]
        assert starts == [None, None, 60000]
        assert [m['status'] for m in messages if m['type'] == 'status'] == ['connecting', 'live', 'polling', 'connecting']
        assert [m['sequence'] for m in messages] == list(range(1, len(messages) + 1))
        assert next(m['bar'] for m in messages if m['type'] == 'bar')['closed'] is False
    finally:
        await market.close()


def worker_input():
    start=1700000000000
    return {'source':'''//@version=6
strategy("Contract", overlay=true, initial_capital=10000, commission_type=strategy.commission.percent, commission_value=0.1)
if bar_index == 2
    strategy.entry("L", strategy.long, qty=2)
if bar_index == 6
    strategy.close("L")
''','request':{'script_id':'test','script_version':1,'symbol':'binance:spot:BTCUSDT','timeframe':'1m','start':start,'end':start+600000,'inputs':{},'props':{}},
        'symbol':{'id':'binance:spot:BTCUSDT','symbol':'BTCUSDT','name':'BTC/USDT','market':'spot','exchange':'binance','currency':'USDT','timeframes':['1m'],
            'timezone':'Etc/UTC','session':'24x7','close_only':False,'metadata':{'mintick':.01,'minmove':1,'pricescale':100,'mincontract':.00001,'pointvalue':1}},
        'bars':[{'time':start+i*60000,'closeTime':start+(i+1)*60000,'open':100+i,'high':102+i,'low':99+i,'close':101+i,'volume':100,'closed':True} for i in range(10)]}


def execute_worker(folder,payload):
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'input.json').write_text(json.dumps(payload),encoding='utf-8')
    result=subprocess.run([r'D:\Tools\NodeJS\node.exe',str(ROOT/'frontend/scripts/pine-workspace-worker.mjs'),str(folder)],
        capture_output=True,text=True,timeout=30)
    return result,json.loads((folder/('result.json' if result.returncode==0 else 'error.json')).read_text(encoding='utf-8'))


def test_pine_worker_raw_fills_and_costs(tmp_path):
    result,data=execute_worker(tmp_path,worker_input())
    assert result.returncode==0,data
    assert len(data['trades'])==1
    assert data['trades'][0]['entry_price']==103
    assert data['trades'][0]['exit_price']==107
    assert data['summary']['netprofit']==pytest.approx(7.58)
    assert data['summary']['commission']==pytest.approx(.42)
    assert [f['fill_bar'] for f in data['fills']]==[3,7]
    assert [f['qty'] for f in data['fills']]==[2,2]
    assert len(data['equity'])==10
    assert data['equity'][-1]['equity']==pytest.approx(10007.58)


def test_pine_worker_rejects_indicator_and_unsupported(tmp_path):
    payload=worker_input()
    payload['source']='//@version=6\nindicator("I")\nplot(close)'
    result,data=execute_worker(tmp_path/'indicator',payload)
    assert result.returncode==1 and 'strategy()' in data['error']
    payload['source']='//@version=6\nstrategy("S")\nstrategy.entry("L",strategy.long,oca_name="group")'
    result,data=execute_worker(tmp_path/'oca',payload)
    assert result.returncode==1 and 'OCA' in data['error']


def test_pine_worker_preserves_unclosed_position(tmp_path):
    payload=worker_input()
    payload['source']='//@version=5\nstrategy("Open", initial_capital=10000)\nif bar_index==2\n    strategy.entry("L", strategy.long, qty=1)'
    result,data=execute_worker(tmp_path,payload)
    assert result.returncode==0
    assert not data['trades'] and len(data['open_trades'])==1
    assert data['summary']['position_size']==1


@pytest.mark.asyncio
async def test_runs_complete_and_snapshot_rerun(tmp_path,monkeypatch):
    payload=worker_input()
    store=ChartWorkspaceStore(tmp_path)
    store.put('scripts','test',WorkspaceWrite(name='S',data={'source':payload['source']}))
    class Market:
        async def resolve(self,key):return ChartSymbol.model_validate(payload['symbol'])
        async def bars(self,*args,**kwargs):
            selected=[ChartBar.model_validate(b) for b in payload['bars'] if b['time'] >= kwargs.get('start',0)]
            return ChartBars(symbol=await self.resolve(''),timeframe='1m',bars=selected,source='fixture')
    runs=ChartPineRuns(store,Market())
    first=runs.create(PineRunRequest.model_validate(payload['request']),'http://127.0.0.1:1')
    await runs.tasks[first.id]
    assert runs.get(first.id).status=='completed',runs.get(first.id).error
    assert len(runs.get(first.id).provenance['engine_snapshot'])==64
    def changed_installation(_):
        raise AssertionError('Rerun must not select the current installed runtime')
    monkeypatch.setattr('app.services.chart_workspace_runs.freeze_engine',changed_installation)
    second=runs.create(first.request,'http://127.0.0.1:1',frozen_from=first.id)
    await runs.tasks[second.id]
    assert runs.get(second.id).status=='completed',runs.get(second.id).error
    assert runs.get(second.id).provenance==runs.get(first.id).provenance
    assert not (tmp_path/'research').exists()
    await runs.close()


def test_engine_snapshot_detects_changed_files(tmp_path):
    from app.services.chart_workspace_engine import freeze_engine,engine_worker
    identity=freeze_engine(tmp_path)
    worker=engine_worker(tmp_path,identity)
    worker.write_text('// changed',encoding='utf-8')
    with pytest.raises(ValueError,match='已改变'):
        engine_worker(tmp_path,identity)


def test_cancelled_order_in_same_bar_is_recorded(tmp_path):
    payload=worker_input()
    payload['source']='//@version=6\nstrategy("Cancel")\nif bar_index==2\n    strategy.entry("L", strategy.long, qty=1, limit=80)\n    strategy.cancel("L")'
    result,data=execute_worker(tmp_path,payload)
    assert result.returncode==0,data
    assert not data['fills'] and not data['trades']
    assert len(data['orders'])==1 and data['orders'][0]['status']=='cancelled'


def test_strategy_reverse_pyramid_and_partial_exit(tmp_path):
    payload=worker_input()
    payload['source']='''//@version=6
strategy("Orders", initial_capital=10000, pyramiding=3)
if bar_index==1
    strategy.entry("L",strategy.long,qty=2)
if bar_index==2
    strategy.entry("L2",strategy.long,qty=2)
if bar_index==3
    strategy.close("L",qty=1)
if bar_index==5
    strategy.entry("S",strategy.short,qty=3)
'''
    result,data=execute_worker(tmp_path,payload)
    assert result.returncode==0,data
    assert data['summary']['position_size']==-3
    assert sum(t['size'] for t in data['trades'])==4
    assert len(data['trades'])>=3
    assert len(data['open_trades'])==1


@pytest.mark.asyncio
async def test_gap_inside_page_fails_without_results(tmp_path):
    payload=worker_input()
    store=ChartWorkspaceStore(tmp_path)
    store.put('scripts','test',WorkspaceWrite(name='S',data={'source':payload['source']}))
    class Market:
        async def resolve(self,key):return ChartSymbol.model_validate(payload['symbol'])
        async def bars(self,*args,**kwargs):
            return ChartBars(symbol=await self.resolve(''),timeframe='1m',bars=[ChartBar.model_validate(b) for i,b in enumerate(payload['bars']) if i!=5],source='fixture')
    runs=ChartPineRuns(store,Market())
    item=runs.create(PineRunRequest.model_validate(payload['request']),'http://127.0.0.1:1')
    await runs.tasks[item.id]
    assert runs.get(item.id).status=='failed' and '缺口' in runs.get(item.id).error
    assert not (runs.folder(item.id)/'result.json').exists()
    await runs.close()


@pytest.mark.parametrize("kind,exit_code,third,expected", [
    ("stop", 'strategy.exit("X","L",stop=98,limit=110)', (101,102,97,99), 97.98),
    ("target", 'strategy.exit("X","L",stop=95,limit=105)', (101,106,100,105), 105),
    ("trail", 'strategy.exit("X","L",trail_price=103,trail_offset=100)', (102,105,102,104), 103.98),
])
def test_strategy_exit_prices_and_slippage(tmp_path,kind,exit_code,third,expected):
    payload=worker_input()
    payload['source']='//@version=6\nstrategy("Exit",initial_capital=10000,slippage=2)\nif bar_index==0\n    strategy.entry("L",strategy.long,qty=1)\n'+exit_code
    for bar,prices in zip(payload['bars'],[(100,102,99,101),(101,102,100,101),third]):
        bar.update(zip(['open','high','low','close'],prices))
    result,data=execute_worker(tmp_path,payload)
    assert result.returncode==0,data
    trade=data['trades'][0]
    assert trade['entry_price']==pytest.approx(101.02)
    assert trade['exit_price']==pytest.approx(expected)
    assert data['fills'][1]['qty']==1


def test_limit_entry_does_not_receive_slippage(tmp_path):
    payload=worker_input()
    payload['source']='//@version=6\nstrategy("Limit",slippage=5)\nif bar_index==0\n    strategy.entry("L",strategy.long,qty=1,limit=100)'
    result,data=execute_worker(tmp_path,payload)
    assert result.returncode==0,data
    assert data['fills'][0]['fill_price']==100


@pytest.mark.asyncio
async def test_cancel_loading_and_recover_interrupted(tmp_path):
    payload=worker_input()
    store=ChartWorkspaceStore(tmp_path)
    store.put('scripts','test',WorkspaceWrite(name='S',data={'source':payload['source']}))
    started=asyncio.Event()
    class Market:
        async def resolve(self,key):
            started.set()
            await asyncio.Event().wait()
    runs=ChartPineRuns(store,Market())
    item=runs.create(PineRunRequest.model_validate(payload['request']),'http://127.0.0.1:1')
    await started.wait()
    assert (await runs.cancel(item.id)).status=='cancelled'
    assert not runs.tasks and not runs.processes
    pending={**item.model_dump(),'id':'interrupted-test','status':'running'}
    store.put('runs','interrupted-test',WorkspaceWrite(name='S',data=pending))
    recovered=ChartPineRuns(store,Market())
    assert recovered.get('interrupted-test').status=='interrupted'
    await recovered.close()
