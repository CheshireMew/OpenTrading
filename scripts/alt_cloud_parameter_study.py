"""Frozen transfer test on four new assets, with a small secondary parameter grid.

Uses OpenTrading MarketDataService/KlineStore and the original v4 simulator.
Old experiments and their selection records are never changed.
"""
import argparse
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import product
from math import isclose, prod
import json

from app.domain.backtest_history import validate_observed_bars
from app.domain.local_backtest import simulate
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from app.services.local_backtest_strategies import digest, load_strategy, validate_parameters, environment
from config import settings
from scripts.btc_cloud_parameter_study import BASE, key, freeze
from scripts.cloud_joint_study import gap_sensitivity
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save, metrics
from scripts.trend_cloud_study import stamp

DOCS = ROOT/'docs/verification/alt-cloud-transfer-20260911'
RUNTIME = ROOT/'.opentrading_runtime/alt-cloud-transfer-20260911'
SOURCE = ROOT/'strategies/trend_cloud_parameters_v4.py'
STEP = 900000
END = '2026-09-10T00:00:00Z'
SPLIT = '2024-09-10T00:00:00Z'
ASSETS = {'paxg': ('PAXG/USDT', 2020), 'zec': ('ZEC/USDT', 2019),
          'sol': ('SOL/USDT', 2020), 'bnb': ('BNB/USDT', 2018)}
AXES = dict(center_length=[55, 89], width_length=[31, 50], trigger_mult=[.4, .8],
            chase_mult=[1.5, 2.], activation_pct=[1., 2.], giveback_pct=[50.], initial_stop_pct=[1., 2.])
ETH_PARAMETERS = BASE.copy()
BTC_PARAMETERS = {**BASE, 'width_length': 50, 'trigger_mult': .8, 'chase_mult': 1.5, 'initial_stop_pct': 2.}


def variants():
    return {key(p): {'parameters': p} for values in product(*AXES.values())
            for p in [{**BASE, **dict(zip(AXES, values))}]}


def choose(results, candidates, period='train'):
    return sorted(candidates, key=lambda k: (-results[k][period]['return_pct'], k))


def allowed(stage, period, plan, asset, candidate, lock=None):
    if candidate not in plan['variants'] or asset not in plan['assets']:
        return False
    if stage == 'transfer':
        return candidate in plan['transfer'].values() and period in ('full', 'final')
    if stage == 'train':
        return period == 'train'
    if stage == 'evaluate':
        return lock is not None and asset in lock['assets'] and period in ('full', 'final')
    return False


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Already frozen; resume fetch/run instead')
    assert settings.EXCHANGE_ID == 'binance'
    vs = variants()
    assert len(vs) == 64 and key(ETH_PARAMETERS) in vs and key(BTC_PARAMETERS) in vs
    assets = {a: dict(symbol=s, periods=dict(full=[f'{y}-09-10T00:00:00Z', END],
                         train=[f'{y}-09-10T00:00:00Z', SPLIT], final=[SPLIT, END])) for a,(s,y) in ASSETS.items()}
    plan = dict(created_at=datetime.now(timezone.utc).isoformat(), assets=assets, axes=AXES, variants=vs,
        transfer={'ETH原参数': key(ETH_PARAMETERS), 'BTC原参数': key(BTC_PARAMETERS)},
        warmup=650, timeframe='15m', step_ms=STEP, initial_cash=10000, position_pct=100,
        fees=0, slippage=0, leverage=1, exchange='binance', market='spot',
        source_hash=digest(SOURCE.read_bytes()), engine_hash=digest((ROOT/'app/domain/local_backtest.py').read_bytes()),
        primary='Apply the two already-established ETH/BTC configurations unchanged to PAXG, ZEC, SOL and BNB. Show full-period and last-two-year returns first. This is the primary cross-asset test.',
        secondary='Exactly 64 prespecified joint combinations per asset. Giveback fixed at 50%; other six factors take two values. No expansion. Rank using pre-2024-09-10 data only and lock the first candidate for EACH asset before inspecting secondary final/full results.',
        evaluation='After locking training selections, evaluate every one of the SAME 64 combinations on final and full periods. Full-history top returns are explicitly hindsight rankings; the pre-2024 choice and its later return remain separately identified and never replaced.',
        leakage_limit='The unchanged transfer baselines are evaluated first, including final data. This final period is excluded from the automatic secondary selection rule, but is not a wholly unseen period for the overall research session. No adjustments after any results.',
        assessment='Return only determines ranks. Describe which unchanged configurations are positive on both full and final periods, without treating that as proof of future profitability. Per-asset tuning cannot rescue an unsuccessful unchanged-transfer claim.',
        execution='Original v4 source and engine; close confirmation, next observed open, opposite exits, initial stop, causal profit protection. Both directions simulated on spot candles, no execution venue change.',
        data_policy='All history via project MarketDataService / Binance / KlineStore. Resume chunks; recheck gaps using same service; never fill candles. Strict boundaries and 650 warmup bars for each window.',
        nominal_simulations=64*3*4, environment=environment())
    freeze(DOCS/'plan.json', plan)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME/'strategy.py').write_bytes(SOURCE.read_bytes())
    (RUNTIME/'engine.py').write_bytes((ROOT/'app/domain/local_backtest.py').read_bytes())
    for k,v in vs.items(): freeze(RUNTIME/'configs'/f'{k}.json',v)
    snapshot('037-frozen-four-asset-transfer', [SOURCE, ROOT/'app/domain/local_backtest.py', PathHere(), DOCS/'plan.json'])
    print('Frozen four-asset transfer test; 64 combinations each; 768 asset/parameter/period results.',flush=True)


def PathHere():
    from pathlib import Path
    return Path(__file__)


def fetch_one(asset, info, plan):
    destination=DOCS/'data'/f'{asset}.json'
    if destination.exists():
        record=read(destination)
        assert digest((ROOT/record['path']).read_bytes()) == record['data_hash']
        return asset, record
    start,end=map(stamp, info['periods']['full']); first=start-plan['warmup']*STEP
    db=build_database_runtime(settings)
    market=MarketDataService(exchange_gateway=ExchangeGateway('binance'),kline_store=KlineStore(database_runtime=db))
    date=lambda t:datetime.fromtimestamp(t/1000,timezone.utc)
    combined={};span=60*86400000; chunks=list(range(first,end,span))
    try:
        for i,a in enumerate(chunks):
            b=min(a+span,end);part=RUNTIME/'fetch'/asset/f'{i:03}.json'
            if part.exists():
                chunk=read(part);assert chunk['start']==a and chunk['end']==b
                rows=chunk['rows']
            else:
                rows=market.load_ohlcv_range(info['symbol'],'15m',date(a),date(b-1)).rows
                if not rows: raise ValueError(f'{asset} has no data in chunk {i}')
                save(part,dict(start=a,end=b,rows=rows))
            combined.update({int(r[0]):r for r in rows if first<=r[0]<end})
            print(f'DATA {asset} {i+1}/{len(chunks)}: {len(combined)} candles',flush=True)
        rows=sorted(combined.values(),key=lambda x:x[0]);cursor=first;holes=[]
        for row in rows:
            if row[0]>cursor:holes.append((cursor,int(row[0])))
            cursor=int(row[0])+STEP
        if cursor<end:holes.append((cursor,end))
        rechecks=[]
        for a,b in holes:
            values=market.load_live_ohlcv_range(info['symbol'],'15m',date(a),date(b-1)).rows
            values=[r for r in values if a<=r[0]<b]
            combined.update({int(r[0]):r for r in values})
            if values:market.kline_store.save(market.symbol_routing.storage_symbol(info['symbol']),'15m',values)
            rechecks.append(dict(start=a,end=b,returned=len(values)))
        freeze(DOCS/'data'/f'{asset}-gap-recheck.json',rechecks)
        rows=sorted(combined.values(),key=lambda x:x[0])
        bars,gaps=validate_observed_bars(rows,start,end,STEP,650,stamp(END))
        times=[b.timestamp for b in bars]
        for lo,hi in info['periods'].values():
            a,b=bisect_left(times,stamp(lo)),bisect_left(times,stamp(hi))
            validate_observed_bars(rows[a-650:b],stamp(lo),stamp(hi),STEP,650,stamp(END))
        path=RUNTIME/f'{asset}-data.json';freeze(path,rows)
        record=dict(symbol=info['symbol'],start=info['periods']['full'][0],end=END,
            path=path.relative_to(ROOT).as_posix(),data_hash=digest(path.read_bytes()),gaps=gaps,
            candles=len(bars),missing_bars=sum(g['missing_bars'] for g in gaps),zero_volume_bars=sum(r[5]==0 for r in rows),
            source='Project MarketDataService / Binance spot / KlineStore')
        freeze(destination,record)
        print(f'DATA VERIFIED {asset}: {len(bars)} bars, {len(gaps)} gaps',flush=True)
        return asset,record
    finally:db.dispose()


def fetch(workers):
    plan=read(DOCS/'plan.json');records={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs=[pool.submit(fetch_one,a,v,plan) for a,v in plan['assets'].items()]
        for job in as_completed(jobs):
            asset,record=job.result();records[asset]=record
    freeze(DOCS/'data.json',{a:records[a] for a in plan['assets']})


_state=None


def init_worker(plan,data,provenance):
    global _state
    assert digest((RUNTIME/'strategy.py').read_bytes())==plan['source_hash']
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==plan['engine_hash']
    cache={}
    for a,r in data.items():
        raw=(ROOT/r['path']).read_bytes();assert digest(raw)==r['data_hash']
        bars,gaps=validate_observed_bars(json.loads(raw),stamp(r['start']),stamp(r['end']),STEP,650,stamp(END))
        assert gaps==r['gaps'];cache[a]=(bars,[b.timestamp for b in bars])
    _state=plan,data,provenance,cache


def calculate(task):
    stage,asset,k,period=task;plan,data,provenance,cache=_state
    lock=read(DOCS/'selection-lock.json') if (DOCS/'selection-lock.json').exists() else None
    assert allowed(stage,period,plan,asset,k,lock)
    path=RUNTIME/'traces'/asset/f'{k}-{period}.json'
    if path.exists():
        trace=read(path)
        assert trace['provenance']==provenance and trace['period']==plan['assets'][asset]['periods'][period]
        return asset,k,period,trace['metrics']
    bars,times=cache[asset];start,end=map(stamp,plan['assets'][asset]['periods'][period])
    a,b=bisect_left(times,start),bisect_left(times,end)
    module,spec=load_strategy(RUNTIME/'strategy.py');p=validate_parameters(spec,plan['variants'][k]['parameters'])
    result=simulate(bars[a-650:b],module,p,warmup=650,step_ms=STEP,initial_cash=10000,position_pct=100)
    m=metrics(result);m.pop('daily_equity',None);m.pop('monthly_returns',None)
    m['gap_sensitivity']=gap_sensitivity(result['trades'],[g for g in data[asset]['gaps'] if start<=g['start']<end])
    compound=(prod(1+t['return_pct']/100 for t in result['trades'])-1)*100
    assert isclose(compound,m['return_pct'],rel_tol=1e-8,abs_tol=1e-6)
    assert m['wins']+m['losses']+m['breakeven']==m['total_trades']
    trace={f:result[f] for f in ('report','trades','signals')}
    trace['equity']=[dict(timestamp=x['timestamp'],equity=x['equity']) for x in result['equity']]
    trace.update(metrics=m,parameters=p,asset=asset,phase=stage,period=plan['assets'][asset]['periods'][period],provenance=provenance)
    save(path,trace)
    return asset,k,period,m


def study(workers):
    plan,data=read(DOCS/'plan.json'),read(DOCS/'data.json')
    provenance=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),data_manifest_hash=digest((DOCS/'data.json').read_bytes()),
                    source_hash=plan['source_hash'],engine_hash=plan['engine_hash'],runner_hash=digest(PathHere().read_bytes()))
    path=DOCS/'results.json'
    out=read(path) if path.exists() else dict(plan=plan,data=data,provenance=provenance,results={a:{} for a in plan['assets']},status='running')
    assert out['provenance']==provenance
    if out['status']=='completed':print('Already complete; no new search.',flush=True);return
    with ProcessPoolExecutor(max_workers=workers,initializer=init_worker,initargs=(plan,data,provenance)) as pool:
        def run(stage,keys,periods):
            tasks=[(stage,a,k,p) for a in plan['assets'] for k in keys for p in periods if p not in out['results'][a].get(k,{})]
            jobs=[pool.submit(calculate,t) for t in tasks]
            for i,job in enumerate(as_completed(jobs),1):
                asset,k,period,m=job.result();out['results'][asset].setdefault(k,{})[period]=m
                out['stage']=stage;out['completed_results']=sum(len(v) for r in out['results'].values() for v in r.values());save(path,out)
                if stage=='transfer' or i%8==0 or i==len(tasks):print(f'{stage} {i}/{len(tasks)} | {asset} {period} {k}: {m["return_pct"]:+.2f}%',flush=True)
        run('transfer',list(plan['transfer'].values()),['full','final'])
        freeze(DOCS/'transfer-results.json',{a:{name:{p:out['results'][a][k][p] for p in ('full','final')}
            for name,k in plan['transfer'].items()} for a in plan['assets']})
        run('train',list(plan['variants']),['train'])
        selections={}
        for asset,results in out['results'].items():
            order=choose(results,plan['variants'])
            selections[asset]=dict(selected=order[0],parameters=plan['variants'][order[0]]['parameters'],training_ranking=order,
                                  training_results_hash=digest(json.dumps({k:results[k]['train'] for k in sorted(results)},sort_keys=True).encode()))
        lock=dict(created_at=datetime.now(timezone.utc).isoformat(),assets=selections,provenance=provenance)
        if (DOCS/'selection-lock.json').exists():
            old=read(DOCS/'selection-lock.json');assert old['assets']==selections and old['provenance']==provenance;lock=old
        freeze(DOCS/'selection-lock.json',lock)
        print('TRAINING CHOICES LOCKED: '+json.dumps({a:s['selected'] for a,s in selections.items()}),flush=True)
        run('evaluate',list(plan['variants']),['final','full'])
    out.update(status='completed',selection=lock,completed_at=datetime.now(timezone.utc).isoformat())
    out['rankings']={a:{p:choose(r,plan['variants'],p) for p in ('train','final','full')} for a,r in out['results'].items()}
    assert out['completed_results']==plan['nominal_simulations']
    save(path,out)
    print('COMPLETED 768 results; no retuning.',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','fetch','run']);ap.add_argument('--workers',type=int,choices=[1,2,3,4],default=3);args=ap.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='fetch':fetch(args.workers)
    else:study(args.workers)
