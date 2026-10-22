"""Move the existing better cloud parameter sets across four requested timeframes."""
import argparse
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from math import isclose
from pathlib import Path
from threading import local
import json

from app.domain.local_backtest import simulate
from app.domain.backtest_history import validate_observed_bars
from app.domain.cloud_trade_attribution import summary, compound, calendar_returns, periods, stress
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from app.services.local_backtest_strategies import digest, load_strategy, validate_parameters, environment
from config import settings
from scripts.alt_cloud_parameter_study import ETH_PARAMETERS
from scripts.btc_cloud_parameter_study import freeze
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/cloud-timeframe-20260911'
RUNTIME=ROOT/'.opentrading_runtime/cloud-timeframe-20260911'
SOURCE=ROOT/'strategies/trend_cloud_timeframe_v6.py'
DEPENDENCY=ROOT/'strategies/trend_cloud_parameters_v4.py'
PRIOR={'alt':ROOT/'docs/verification/alt-cloud-transfer-20260911', 'repair':ROOT/'docs/verification/paxg-zec-repair-20260911'}
ASSETS=['paxg','zec'];TFS=['5m','15m','30m','1h','1d']
STEPS={'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'1d':86400000}
WARMUP=650;DAY=86400000;END='2026-09-10T00:00:00Z';COMMON='2022-09-10T00:00:00Z';RECENT='2024-09-10T00:00:00Z'


def utc():return datetime.now(timezone.utc).isoformat()
def date(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()


def candidates():
    old={label:read(path/'results.json') for label,path in PRIOR.items()};result={}
    module,meta=load_strategy(SOURCE)
    for a in ASSETS:
        pool={}
        for label,r in old.items():
            for key,ps in r['results'][a].items():
                if 'full' not in ps:continue
                spec=r['variants'][a][key] if label=='repair' else r['plan']['variants'][key]
                p=validate_parameters(meta,spec['parameters']);ident=json.dumps(p,sort_keys=True)
                item=dict(parameters=p,origin=label,origin_key=key,old_full_return=ps['full']['return_pct'],old_recent_return=ps['final']['return_pct'])
                if ident not in pool:pool[ident]=item
                else:assert isclose(pool[ident]['old_full_return'],item['old_full_return'],abs_tol=1e-7)
        ranked=sorted(pool.values(),key=lambda x:(-x['old_full_return'],json.dumps(x['parameters'],sort_keys=True)))
        recent=max(pool.values(),key=lambda x:x['old_recent_return'])
        base=next(x for x in pool.values() if x['parameters']==validate_parameters(meta,ETH_PARAMETERS))
        specs=[('base','原ETH六年第一参数',base),('full1','该币原15分钟全历史第1组',ranked[0]),('full2','该币原15分钟全历史第2组',ranked[1]),('recent1','该币原15分钟后两年第1组',recent)]
        result[a]={k:dict(**v,label=label) for k,label,v in specs}
        assert len({json.dumps(v['parameters'],sort_keys=True) for v in result[a].values()})==4
    return result


def prepare():
    if (DOCS/'plan.json').exists():print('Already frozen');return
    old_data=read(PRIOR['alt']/'data.json')
    plan=dict(created_at=utc(),assets=ASSETS,variants=candidates(),timeframes=TFS,requested_timeframes=['5m','30m','1h','1d'],
        old_data={a:old_data[a] for a in ASSETS},common=[COMMON,END],recent=[RECENT,END],warmup=WARMUP,
        source_hash=digest(SOURCE.read_bytes()),dependency_hash=digest(DEPENDENCY.read_bytes()),engine_hash=digest((ROOT/'app/domain/local_backtest.py').read_bytes()),runner_hash=digest(Path(__file__).read_bytes()),
        historical_selection_hashes={k:digest((v/'results.json').read_bytes()) for k,v in PRIOR.items()},environment=environment(),
        rule='Preserve original EMA(hl2) centre, EMA(high-low) width, close crossing, anti-chase, opposite exit, initial stop and percentage profit protection. Only replace candle timeframe; periods remain counts of bars, not constant clock duration. No new momentum, moving-average crossover or Donchian rules.',
        selection='Per coin, before viewing new timeframe results: original ETH6-year winner as control, top2 unique parameter sets by already-observed original15m full-history return pooled across prior alt/repair studies, and best original15m last2year parameter set. Exactly4 per coin; no expansion, no parameter retuning on new timeframe outcomes.',
        adaptation='Only required v5 implementation fix: its hardcoded900000ms consecutive confirmation becomes the observed native timeframe interval. v6 is an independent copy; old v4/v5 untouched. Defaults reproduce v4;15m confirmation reproduces v5. ATR stop is used only if already present in selected parameters.',
        data='Use project MarketDataService/KlineStore native Binance spot candles.5m cannot be reconstructed from15m. Store bounded download checkpoints. Existing15m immutable snapshot is control. Retain missing bars and recheck actual gaps via project service; no invented listing data.650 contiguous warmup bars unchanged.',
        periods='Common2022-09-10→2026-09-10 for all4 requested timeframes plus15m control; this allows650 daily warmup bars for PAXG. Also evaluate each available full history and last2years. Longer history begins at original6/7year start if warmup exists, otherwise first UTC day supporting650 contiguous warmup. Different full-history starts must be labelled; main ranking uses common4years only.',
        validation='Parameters selected from already-studied15m results, including later years. New-timeframe/last2year results are sensitivity comparisons, not untouched holdouts. No rolling re-selection, no separate strategy per year. Report per-year continuous equity, win/loss counts, holding times and exit causes.',
        costs=dict(fees=0,slippage=0,leverage=1,initial_cash=10000,position_pct=100),
        execution='Signal at candle close; next observed open fills. Initial stop/profit protection are evaluated by the unchanged project simulator using the selected timeframe OHLC, not15m signals. Large-bar intrabar uncertainty and unobservable gap intervals are disclosed, never claimed as tick-level execution.',
        total_simulations=120)
    freeze(DOCS/'plan.json',plan)
    snapshot('048-frozen-original-cloud-timeframes',[DOCS/'plan.json',SOURCE,DEPENDENCY,ROOT/'strategies/trend_cloud_atr_confirm_v5.py',ROOT/'app/domain/local_backtest.py',Path(__file__),ROOT/'test/test_cloud_timeframe.py'])
    print('FROZEN:2 assets x4 existing parameter sets x(4 requested timeframes+15m control) x3 periods =120',flush=True)


_thread=local();_databases=[]
def fetch_worker():
    db=build_database_runtime(settings);_databases.append(db)
    _thread.market=MarketDataService(exchange_gateway=ExchangeGateway('binance'),kline_store=KlineStore(database_runtime=db))


def fetch_chunk(task):
    a,tf,start,end,symbol=task;dest=RUNTIME/'fetch'/a/tf/f'{start}-{end}.json'
    if dest.exists():return read(dest)
    dt=lambda t:datetime.fromtimestamp(t/1000,timezone.utc)
    rows=_thread.market.load_ohlcv_range(symbol,tf,dt(start),dt(end-1)).rows
    rows=[x for x in rows if start<=x[0]<end]
    record=dict(asset=a,timeframe=tf,start=start,end=end,rows=rows);save(dest,record)
    return record


def safe_start(rows,desired,step):
    for i in range(WARMUP,len(rows)):
        t=int(rows[i][0])
        if t>=desired and t%DAY==0 and t-rows[i-WARMUP][0]==WARMUP*step:return t
    raise ValueError('Cannot find sufficient contiguous warmup')


def fetch(workers):
    plan=read(DOCS/'plan.json')
    if (DOCS/'data.json').exists():print('Data already frozen');return
    tasks=[];combined={(a,tf):{} for a in ASSETS for tf in TFS if tf!='15m'}
    for a in ASSETS:
        old=plan['old_data'][a]
        for tf in TFS:
            if tf=='15m':continue
            step=STEPS[tf];lo=stamp(old['start'])-WARMUP*step;end=stamp(END)
            for start in range(lo,end,10000*step):tasks.append((a,tf,start,min(end,start+10000*step),old['symbol']))
    try:
        with ThreadPoolExecutor(max_workers=workers,initializer=fetch_worker) as pool:
            jobs=[pool.submit(fetch_chunk,t) for t in tasks]
            for n,job in enumerate(as_completed(jobs),1):
                r=job.result();combined[r['asset'],r['timeframe']].update({int(x[0]):x for x in r['rows']})
                print(f'DATA {n}/{len(jobs)} {r["asset"]}/{r["timeframe"]} {date(r["start"])[:10]} {len(r["rows"])} bars',flush=True)
    finally:
        for db in _databases:db.dispose()
    data={};db=build_database_runtime(settings);market=MarketDataService(exchange_gateway=ExchangeGateway('binance'),kline_store=KlineStore(database_runtime=db))
    try:
        for a in ASSETS:
            data[a]={};old=plan['old_data'][a]
            for tf in TFS:
                step=STEPS[tf];end=stamp(END)
                if tf=='15m':rows=read(ROOT/old['path']);assert digest((ROOT/old['path']).read_bytes())==old['data_hash'];rechecks=[]
                else:
                    merged=combined[a,tf];rows=sorted(merged.values(),key=lambda x:x[0]);holes=[]
                    for x,y in zip(rows,rows[1:]):
                        if y[0]>x[0]+step:holes.append((int(x[0]+step),int(y[0])))
                    if rows[-1][0]+step<end:holes.append((int(rows[-1][0]+step),end))
                    rechecks=[]
                    for lo,hi in holes:
                        values=market.load_live_ohlcv_range(old['symbol'],tf,datetime.fromtimestamp(lo/1000,timezone.utc),datetime.fromtimestamp((hi-1)/1000,timezone.utc)).rows
                        values=[x for x in values if lo<=x[0]<hi];merged.update({int(x[0]):x for x in values})
                        if values:market.kline_store.save(market.symbol_routing.storage_symbol(old['symbol']),tf,values)
                        rechecks.append(dict(start=lo,end=hi,returned=len(values)))
                    rows=sorted(merged.values(),key=lambda x:x[0])
                assert rows[-1][0]==end-step,(a,tf,'tail missing')
                _,gaps=validate_observed_bars(rows,int(rows[0][0]),end,step,0,end)
                start=safe_start(rows,stamp(old['start']),step)
                assert start<=stamp(COMMON),(a,tf,'insufficient common history')
                ps=dict(common=[COMMON,END],full=[date(start),END],recent=[RECENT,END])
                times=[x[0] for x in rows]
                for lo,hi in ps.values():
                    i,j=bisect_left(times,stamp(lo)),bisect_left(times,stamp(hi))
                    validate_observed_bars(rows[i-WARMUP:j],stamp(lo),stamp(hi),step,WARMUP,end)
                path=RUNTIME/'data'/f'{a}-{tf}.json';freeze(path,rows)
                data[a][tf]=dict(path=path.relative_to(ROOT).as_posix(),data_hash=digest(path.read_bytes()),rows=len(rows),gaps=gaps,missing=sum(g['missing_bars'] for g in gaps),
                                 zero_volume=sum(x[5]==0 for x in rows),periods=ps,gap_recheck=rechecks)
                print('VALID',a,tf,'full',ps['full'],'rows',len(rows),'missing',data[a][tf]['missing'],flush=True)
        freeze(DOCS/'data.json',data)
    finally:db.dispose()


_state=None
def init_worker(plan,data,provenance):
    global _state
    cache={}
    for a in ASSETS:
        for tf in TFS:
            rec=data[a][tf];raw=(ROOT/rec['path']).read_bytes();assert digest(raw)==rec['data_hash']
            rows=json.loads(raw);bars,gaps=validate_observed_bars(rows,int(rows[0][0]),stamp(END),STEPS[tf],0,stamp(END));cache[a,tf]=(bars,[b.timestamp for b in bars])
    _state=plan,data,provenance,cache


def calculate(task):
    a,k,tf,period=task;plan,data,prov,cache=_state;dest=RUNTIME/'traces'/a/f'{k}-{tf}-{period}.json'
    if dest.exists():
        old=read(dest);assert old['provenance']==prov;return a,k,tf,period,old['metrics']
    bars,times=cache[a,tf];lo,hi=data[a][tf]['periods'][period];i,j=bisect_left(times,stamp(lo)),bisect_left(times,stamp(hi))
    assert i>=WARMUP and times[i]-times[i-WARMUP]==WARMUP*STEPS[tf]
    module,meta=load_strategy(SOURCE);p=validate_parameters(meta,plan['variants'][a][k]['parameters'])
    result=simulate(bars[i-WARMUP:j],module,p,warmup=WARMUP,step_ms=STEPS[tf],initial_cash=10000,position_pct=100)
    m=summary(result['trades']);m.update(return_pct=result['report']['return_pct'],max_drawdown_pct=result['report']['max_drawdown_pct'],
        exits={reason:summary([t for t in result['trades'] if t['exit_reason']==reason]) for reason in sorted({t['exit_reason'] for t in result['trades']})},
        sides={s:summary([t for t in result['trades'] if t['side']==s]) for s in ('long','short')})
    assert isclose(m['compound_return_pct'],m['return_pct'],rel_tol=1e-9,abs_tol=1e-7)
    trace={f:result[f] for f in ('report','trades','signals')};trace['equity']=[dict(timestamp=x['timestamp'],equity=x['equity']) for x in result['equity']]
    if tf=='15m' and period in ('full','recent'):
        prior=plan['variants'][a][k];label=prior['origin'];folder='paxg-zec-repair-20260911' if label=='repair' else 'alt-cloud-transfer-20260911'
        old=read(ROOT/f'.opentrading_runtime/{folder}/traces/{a}/{prior["origin_key"]}-{"full" if period=="full" else "final"}.json')
        for field in ('report','trades','signals','equity'):assert trace[field]==old[field],f'15m mismatch {a}/{k}/{period}/{field}'
        m['legacy_exact']=True
    trace.update(metrics=m,parameters=p,period=[lo,hi],timeframe=tf,provenance=prov);save(dest,trace)
    return a,k,tf,period,m


def study(workers):
    plan=read(DOCS/'plan.json');data=read(DOCS/'data.json')
    for path,key in [(SOURCE,'source_hash'),(DEPENDENCY,'dependency_hash'),(ROOT/'app/domain/local_backtest.py','engine_hash'),(Path(__file__),'runner_hash')]:assert digest(path.read_bytes())==plan[key]
    prov=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),data_hash=digest((DOCS/'data.json').read_bytes()),source_hash=plan['source_hash'],engine_hash=plan['engine_hash'],runner_hash=plan['runner_hash'])
    dest=DOCS/'results.json';out=read(dest) if dest.exists() else dict(status='running',plan=plan,data=data,provenance=prov,results={a:{} for a in ASSETS})
    assert out['provenance']==prov
    if out['status']=='completed':print('Already completed');return
    tasks=[(a,k,tf,p) for a in ASSETS for k in plan['variants'][a] for tf in TFS for p in ('common','full','recent') if p not in out['results'][a].get(k,{}).get(tf,{})]
    with ProcessPoolExecutor(max_workers=workers,initializer=init_worker,initargs=(plan,data,prov)) as pool:
        jobs=[pool.submit(calculate,t) for t in tasks]
        for n,job in enumerate(as_completed(jobs),1):
            a,k,tf,p,m=job.result();out['results'][a].setdefault(k,{}).setdefault(tf,{})[p]=m;save(dest,out)
            print(f'RUN {n}/{len(jobs)} {a}/{k}/{tf}/{p} {m["return_pct"]:+.2f}% {m["trades"]} trades',flush=True)
    out.update(status='completed',completed_at=utc(),simulations=sum(len(ps) for ks in out['results'].values() for fs in ks.values() for ps in fs.values()))
    assert out['simulations']==plan['total_simulations'];save(dest,out)


def audit():
    r=read(DOCS/'results.json');assert r['status']=='completed';details={};checks=[]
    for a in ASSETS:
        details[a]={}
        for tf in TFS:
            raw=read(ROOT/r['data'][a][tf]['path'])
            for k in r['plan']['variants'][a]:
                details[a].setdefault(k,{})[tf]={}
                for period,m in r['results'][a][k][tf].items():
                    path=RUNTIME/'traces'/a/f'{k}-{tf}-{period}.json';t=read(path)
                    assert t['provenance']==r['provenance'];assert len(t['trades'])==m['trades']==m['wins']+m['losses']+m['flat']
                    assert isclose(compound(x['return_pct'] for x in t['trades']),m['return_pct'],rel_tol=1e-9,abs_tol=1e-6)
                    assert isclose(t['equity'][-1]['equity'],10000*(1+m['return_pct']/100),rel_tol=1e-9,abs_tol=1e-6)
                    assert sum(x['trades'] for x in m['exits'].values())==m['trades']
                    checks.append(dict(path=str(path.relative_to(ROOT)),hash=digest(path.read_bytes())))
                    lo,hi=map(stamp,t['period']);eq=t['equity'];stride=max(1,len(eq)//300);curve=eq[::stride]
                    if curve[-1]!=eq[-1]:curve.append(eq[-1])
                    details[a][k][tf][period]=dict(years=calendar_returns(eq,raw,periods(lo,hi,'year')),
                        market=calendar_returns(eq,raw,[('full',lo,hi)])[0],curve=[[x['timestamp'],x['equity']/10000] for x in curve])
            print('AUDIT',a,tf,flush=True)
    legacy=all(r['results'][a][k]['15m'][p]['legacy_exact'] for a in ASSETS for k in r['plan']['variants'][a] for p in ('full','recent'))
    assert legacy;freeze(DOCS/'details.json',details);freeze(DOCS/'verification.json',dict(status='passed',traces_checked=len(checks),legacy_15m_exact=legacy,manifest=checks))
    print('VERIFIED',len(checks),'traces;16 original15m full/recent reports match exactly',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','fetch','run','audit']);p.add_argument('--workers',type=int,default=3);args=p.parse_args()
    {'prepare':prepare,'fetch':lambda:fetch(args.workers),'run':lambda:study(args.workers),'audit':audit}[args.action]()
