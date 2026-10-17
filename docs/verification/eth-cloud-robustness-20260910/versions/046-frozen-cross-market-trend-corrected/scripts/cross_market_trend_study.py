"""Twelve fixed trend rules, native 4h/daily data, chronological/asset holdouts."""
import argparse
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor,ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
from math import isclose
from pathlib import Path
from statistics import median
import json

from app.domain.backtest_history import validate_observed_bars
from app.domain.local_backtest import simulate
from app.domain.cloud_trade_attribution import summary,compound,calendar_returns,periods,stress
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from app.services.local_backtest_strategies import digest,load_strategy,validate_parameters,inspect_strategy,environment
from config import settings
from scripts.btc_cloud_parameter_study import freeze,BASE
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT,read,save
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/cross-market-trend-20260911-r2'
RUNTIME=ROOT/'.heimdall_runtime/cross-market-trend-20260911-r2'
PRIOR=ROOT/'docs/verification/cross-market-trend-20260911'
SOURCE=ROOT/'strategies/cross_market_trend_v1.py'
OLD_SOURCE=ROOT/'strategies/trend_cloud_parameters_v4.py'
DAY=86400000;STEPS={'4h':14400000,'1d':DAY,'15m':900000}
END='2026-09-10T00:00:00Z';COMMON='2021-09-10T00:00:00Z';WARMUP=200
ASSETS=['eth','btc','sol','bnb','paxg','zec'];FOLDS=[2023,2024,2025]


def date(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def utc():return datetime.now(timezone.utc).isoformat()
def anniversary(y):return f'{y}-09-10T00:00:00Z'


def variants():
    module,meta=load_strategy(SOURCE);out={}
    for tf in ('4h','1d'):
        for speed in ('fast','slow'):
            configurations={
                'breakout':dict(entry_length=20 if speed=='fast' else 55,exit_length=10 if speed=='fast' else 20),
                'average':dict(fast_length=20 if speed=='fast' else 50,slow_length=60 if speed=='fast' else 150),
                'momentum':dict(entry_length=30 if speed=='fast' else 90)}
            for family,values in configurations.items():
                p=validate_parameters(meta,dict(family=family,**values,record_indicators=False))
                key=f'{family}_{speed}_{tf}'
                out[key]=dict(parameters=p,timeframe=tf,family=family,speed=speed)
    assert len(out)==12
    return out


def prepare():
    if (DOCS/'plan.json').exists():print('Plan already frozen.');return
    inspect_strategy(SOURCE.read_bytes(),SOURCE.name)
    old=read(ROOT/'docs/verification/cloud-transfer-diagnosis-20260911/plan.json')['data']
    correction=read(PRIOR/'native-cache-correction-applied.json')
    assert variants()==read(PRIOR/'plan.json')['variants']
    plan=dict(created_at=utc(),variants=variants(),assets=ASSETS,old_data={a:old[a] for a in ASSETS},
        revision=dict(reason='Two confirmed stale BTC native candles corrected through project KlineStore; unchanged12 rules and parameters. Preserve all original results and traces.',
                      previous_plan=str((PRIOR/'plan.json').relative_to(ROOT)),previous_plan_hash=digest((PRIOR/'plan.json').read_bytes()),
                      corrections=correction,receipt_hash=digest((PRIOR/'native-cache-correction-applied.json').read_bytes())),
        common=[COMMON,END],desired_full={a:[old[a]['start'],END] for a in ASSETS},
        source_hash=digest(SOURCE.read_bytes()),old_source_hash=digest(OLD_SOURCE.read_bytes()),
        engine_hash=digest((ROOT/'app/domain/local_backtest.py').read_bytes()),
        runner_hash=digest(Path(__file__).read_bytes()),environment=environment(),
        warmup=WARMUP,folds=FOLDS,initial_cash=10000,position_pct=100,fees=0,slippage=0,leverage=1,
        question='Can fixed trend rules on 4h/daily bars transfer between six assets better than the prior 15m cloud strategy?',
        rules='Breakout: close beyond previous20/55-bar high/low; exit on previous10/20-bar opposite extreme. Averages: simple moving average20/60 or50/150; first eligible close adopts current regime, later entries/reversals only on regime changes; equality exits. Momentum: close versus30/90 bars ago; same regime rules. Stop then wait for fresh trigger; breakout can retrigger on a new qualifying breakout. No percentage profit protection, no target/trailing stop, no pyramiding.',
        stops='All12 use Wilder ATR14 x3 fixed absolute initial distance, known at signal close, anchored at actual next-open fill. Never widen after entry. Native-timeframe opposite exit at next open; old initial stop always live intrabar. No new ATR parameter search.',
        data='Native Binance spot4h/daily candles via project MarketDataService/KlineStore; fetch existing desired start minus200days to fixed end. No manufactured listing history or missing bars. Keep per-request checkpoints; recheck observed internal gaps once. The12 rules use200 observed contiguous warmup bars per slice. Longer full start is the first UTC day on/after old start with sufficient contiguous warmup in BOTH native timeframes. Keep common2021-09→2026-09 only if all six data sets support it; otherwise stop rather than silently shorten.',
        selection='For each test year2023/2024/2025 (Sep10→Sep10), train from common2021 start to that year. Eligible if strictly positive return on a majority of training assets (4of6 or3of5) and positive median return. Rank eligible by median return, then key. Same global winner applies unchanged to all6; if none passes, cash for that year. Do not rank by win rate or max drawdown.',
        leave_one_out='Separately for each held asset and each year, use only the other5 assets preceding the test-year boundary to choose by the identical rule. No held-asset return participates in that choice. The chosen rule is tested only on that held asset in the next year. These are transfer diagnostics, not six asset-specific tuning permissions.',
        lock='Write each chronological fold choice for all6 and each leave-one-out choice BEFORE any new variant next-year evaluation. Existing history was studied before; this does not make it untouched history. After the three folds, evaluate all12 continuously over common5years and each available longer history, and show annual rows. Full-history rank is hindsight only and cannot change earlier choices.',
        comparison='Old EMA55 parameters unchanged, rerun on identical common and longer periods using original15m snapshots; annual boundary resets match adaptive evaluation. Buy/hold measured from first bar open to last close. Single-asset independent100%-capital accounts; median across assets is not portfolio return. No volatility-based allocation or leverage added.',
        reporting='Per asset and variant: return, wins/losses/flat, win rate, mean win/loss, holding time, drawdown, both directions, exit reasons, annual equity returns; remove top10 winners as arithmetic sensitivity. Compare each chosen chronological track and leave-one-asset-out track; show performance with best asset omitted. Nearby fast/slow alternatives are shown, not subsequently optimized.',
        stopping='Exactly12 new configurations. No follow-up tuning after outcomes; preserve all failed versions and every executed trade. No claim that positive history guarantees future profitability or that every year must win. No live orders or automated follow-up.')
    freeze(DOCS/'plan.json',plan)
    for name,path in [('strategy.py',SOURCE),('old_strategy.py',OLD_SOURCE),('engine.py',ROOT/'app/domain/local_backtest.py')]:
        dst=RUNTIME/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(path.read_bytes())
    snapshot('046-frozen-cross-market-trend-corrected',[DOCS/'plan.json',SOURCE,OLD_SOURCE,ROOT/'app/domain/local_backtest.py',Path(__file__),ROOT/'test/test_cross_market_trend.py',ROOT/'scripts/cross_market_native_recheck.py'])
    print('FROZEN 12 variants; common5years + available longer histories; 3 chronological folds and6 held-asset folds each.',flush=True)


def safe_start(rows,earliest,step,warmup=WARMUP):
    for i in range(warmup,len(rows)):
        t=int(rows[i][0])
        if t>=earliest and t%DAY==0 and t-int(rows[i-warmup][0])==warmup*step:return t
    raise ValueError('No start with enough contiguous warmup')


def fetch_one(a,tf,plan):
    dest=DOCS/'data'/f'{a}-{tf}.json'
    if dest.exists():
        rec=read(dest);assert digest((ROOT/rec['path']).read_bytes())==rec['data_hash'];return a,tf,rec
    desired,end=map(stamp,plan['desired_full'][a]);first=desired-WARMUP*DAY;step=STEPS[tf]
    db=build_database_runtime(settings)
    market=MarketDataService(exchange_gateway=ExchangeGateway('binance'),kline_store=KlineStore(database_runtime=db))
    symbol=plan['old_data'][a]['symbol'];combined={};to_dt=lambda t:datetime.fromtimestamp(t/1000,timezone.utc)
    try:
        bounds=list(range(first,end,180*DAY))
        for i,start in enumerate(bounds):
            finish=min(end,start+180*DAY);p=RUNTIME/'fetch'/a/tf/f'{i:03}.json'
            if p.exists():
                saved=read(p);assert saved['start']==start and saved['end']==finish;rows=saved['rows']
            else:
                rows=market.load_ohlcv_range(symbol,tf,to_dt(start),to_dt(finish-1)).rows
                save(p,dict(start=start,end=finish,rows=rows))
            combined.update({int(x[0]):x for x in rows if first<=x[0]<end})
            print(f'DATA {a}/{tf} {i+1}/{len(bounds)} {len(combined)} bars',flush=True)
        if not combined:raise ValueError(f'{a}/{tf} no native data')
        rows=sorted(combined.values(),key=lambda x:x[0]);holes=[]
        for left,right in zip(rows,rows[1:]):
            if right[0]>left[0]+step:holes.append((int(left[0]+step),int(right[0])))
        if rows[-1][0]+step<end:holes.append((int(rows[-1][0]+step),end))
        checks=[]
        for start,finish in holes:
            values=market.load_live_ohlcv_range(symbol,tf,to_dt(start),to_dt(finish-1)).rows
            values=[x for x in values if start<=x[0]<finish]
            combined.update({int(x[0]):x for x in values})
            if values:market.kline_store.save(market.symbol_routing.storage_symbol(symbol),tf,values)
            checks.append(dict(start=start,end=finish,returned=len(values)))
        rows=sorted(combined.values(),key=lambda x:x[0])
        assert rows[-1][0]==end-step
        # Validate every observed candle and every internal gap, without a
        # fictitious prefix before listing. Slice warmup is checked separately.
        bars,gaps=validate_observed_bars(rows,int(rows[0][0]),end,step,0,end)
        first_safe=safe_start(rows,desired,step)
        path=RUNTIME/'data'/f'{a}-{tf}.json';freeze(path,rows)
        rec=dict(symbol=symbol,timeframe=tf,path=path.relative_to(ROOT).as_posix(),data_hash=digest(path.read_bytes()),
            first_observed=rows[0][0],first_safe_start=first_safe,end=END,rows=len(rows),gaps=gaps,
            missing=sum(g['missing_bars'] for g in gaps),zero_volume=sum(x[5]==0 for x in rows),gap_recheck=checks,
            source='Project MarketDataService / Binance native spot candles / KlineStore')
        freeze(dest,rec);return a,tf,rec
    finally:db.dispose()


def fetch(workers):
    plan=read(DOCS/'plan.json');data={a:{} for a in ASSETS}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs=[pool.submit(fetch_one,a,tf,plan) for a in ASSETS for tf in ('4h','1d')]
        for job in as_completed(jobs):
            a,tf,r=job.result();data[a][tf]=r
    for a in ASSETS:
        rows={tf:read(ROOT/data[a][tf]['path']) for tf in ('4h','1d')}
        start=max(data[a][tf]['first_safe_start'] for tf in rows)
        while True:
            moved=max(safe_start(rows[tf],start,STEPS[tf]) for tf in rows)
            if moved==start:break
            start=moved
        assert start<=stamp(COMMON),f'{a}: common history unavailable; do not silently shorten'
        ps={'common':[COMMON,END],'full':[date(start),END]}
        ps.update({f'year{y}':[anniversary(y),anniversary(y+1)] for y in range(2021,2026)})
        ps.update({f'train{y}':[COMMON,anniversary(y)] for y in FOLDS})
        for tf in rows:
            ts=[r[0] for r in rows[tf]]
            for lo,hi in ps.values():
                x,z=bisect_left(ts,stamp(lo)),bisect_left(ts,stamp(hi))
                validate_observed_bars(rows[tf][x-WARMUP:z],stamp(lo),stamp(hi),STEPS[tf],WARMUP,stamp(END))
        data[a]['periods']=ps
        print(f'VALID {a}: longer history {date(start)} →{END}',flush=True)
    freeze(DOCS/'data.json',data)


def choose(rows,keys,assets,period):
    ranking=[];required=len(assets)//2+1
    for k in keys:
        rs=[rows[a][k][period]['return_pct'] for a in assets]
        ranking.append(dict(key=k,positive=sum(x>0 for x in rs),median_return_pct=median(rs)))
    ranking.sort(key=lambda x:(-x['median_return_pct'],x['key']))
    eligible=[x for x in ranking if x['positive']>=required and x['median_return_pct']>0]
    return dict(selected=eligible[0]['key'] if eligible else None,assets=list(assets),period=period,ranking=ranking)


_state=None
def init_worker(plan,data,prov):
    global _state
    cache={}
    for a in ASSETS:
        cache[a]={}
        for tf in ('4h','1d','15m'):
            d=plan['old_data'][a] if tf=='15m' else data[a][tf]
            raw=(ROOT/d['path']).read_bytes();assert digest(raw)==d['data_hash'];rows=json.loads(raw)
            bars,gaps=validate_observed_bars(rows,int(rows[0][0]),stamp(END),STEPS[tf],0,stamp(END))
            cache[a][tf]=(bars,[b.timestamp for b in bars])
    _state=plan,data,prov,cache


def calculate(task):
    a,k,period=task;plan,data,prov,cache=_state;dest=RUNTIME/'traces'/a/f'{k}-{period}.json'
    if dest.exists():
        old=read(dest);assert old['provenance']==prov;return a,k,period,old['metrics']
    if period.startswith('year') and int(period[4:]) in FOLDS and k!='old_ema55':assert (DOCS/f'choices-{period[4:]}.json').exists()
    old=k=='old_ema55';tf='15m' if old else plan['variants'][k]['timeframe'];warmup=650 if old else WARMUP
    bars,times=cache[a][tf];lo,hi=data[a]['periods'][period];start,end=stamp(lo),stamp(hi)
    i,j=bisect_left(times,start),bisect_left(times,end)
    assert times[i]==start and times[j-1]==end-STEPS[tf] and i>=warmup
    assert times[i]-times[i-warmup]==warmup*STEPS[tf]
    path=RUNTIME/'old_strategy.py' if old else RUNTIME/'strategy.py';module,meta=load_strategy(path)
    p=BASE if old else plan['variants'][k]['parameters'];p=validate_parameters(meta,p)
    result=simulate(bars[i-warmup:j],module,p,warmup=warmup,step_ms=STEPS[tf],initial_cash=10000,position_pct=100)
    m=summary(result['trades']);m.update(return_pct=result['report']['return_pct'],max_drawdown_pct=result['report']['max_drawdown_pct'],
        exits={reason:summary([x for x in result['trades'] if x['exit_reason']==reason]) for reason in sorted({x['exit_reason'] for x in result['trades']})},
        sides={s:summary([x for x in result['trades'] if x['side']==s]) for s in ('long','short')})
    assert isclose(m['compound_return_pct'],m['return_pct'],rel_tol=1e-9,abs_tol=1e-6)
    trace={f:result[f] for f in ('report','trades','signals','fills')};trace['equity']=[dict(timestamp=x['timestamp'],equity=x['equity']) for x in result['equity']]
    trace.update(provenance=prov,parameters=p,timeframe=tf,period=[lo,hi],metrics=m)
    save(dest,trace);return a,k,period,m


def study(workers):
    plan=read(DOCS/'plan.json');data=read(DOCS/'data.json')
    for path,h in [(SOURCE,plan['source_hash']),(OLD_SOURCE,plan['old_source_hash']),
                   (ROOT/'app/domain/local_backtest.py',plan['engine_hash']),(Path(__file__),plan['runner_hash'])]:assert digest(path.read_bytes())==h
    prov=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),data_hash=digest((DOCS/'data.json').read_bytes()),source_hash=plan['source_hash'],engine_hash=plan['engine_hash'],runner_hash=plan['runner_hash'])
    dest=DOCS/'results.json';out=read(dest) if dest.exists() else dict(status='running',plan=plan,data=data,provenance=prov,results={a:{} for a in ASSETS},choices={})
    assert out['provenance']==prov
    if out['status']=='completed':print('Already complete.');return
    with ProcessPoolExecutor(max_workers=workers,initializer=init_worker,initargs=(plan,data,prov)) as pool:
        def run(stage,requests):
            jobs=[pool.submit(calculate,t) for t in requests if t[2] not in out['results'][t[0]].get(t[1],{})]
            for n,job in enumerate(as_completed(jobs),1):
                a,k,p,m=job.result();out['results'][a].setdefault(k,{})[p]=m;out['stage']=stage;save(dest,out)
                if n%12==0 or n==len(jobs):print(f'{stage} {n}/{len(jobs)} {a}/{k}: {m["return_pct"]:+.2f}%',flush=True)
        for y in FOLDS:
            train=f'train{y}';test=f'year{y}'
            run(train,[(a,k,train) for a in ASSETS for k in plan['variants']])
            choices=dict(global_choice=choose(out['results'],plan['variants'],ASSETS,train),
                held_asset={a:choose(out['results'],plan['variants'],[b for b in ASSETS if b!=a],train) for a in ASSETS},
                input_hash=digest(json.dumps({a:{k:out['results'][a][k][train] for k in plan['variants']} for a in ASSETS},sort_keys=True).encode()),
                test_period=[anniversary(y),anniversary(y+1)])
            freeze(DOCS/f'choices-{y}.json',choices);out['choices'][str(y)]=choices;save(dest,out)
            print(f'LOCKED {y}: {choices["global_choice"]["selected"] or "cash"}; all held-asset choices frozen',flush=True)
            run(test,[(a,k,test) for a in ASSETS for k in plan['variants']])
        run('descriptive',[(a,k,p) for a in ASSETS for k in plan['variants'] for p in ('common','full','year2021','year2022')])
        run('unchanged-old-control',[(a,'old_ema55',p) for a in ASSETS for p in ('common','full',*[f'year{y}' for y in range(2021,2026)])])
    out.update(status='completed',completed_at=utc(),simulations=sum(len(ps) for ks in out['results'].values() for ps in ks.values()))
    save(dest,out);print('COMPLETED',out['simulations'],'simulations; no new configurations.',flush=True)


def track(r,a,choices):
    returns=[];trades=[];cash=10000;annual=[]
    for y in FOLDS:
        k=choices[str(y)];m=r['results'][a][k][f'year{y}'] if k else None
        annual.append(dict(year=y,key=k,return_pct=m['return_pct'] if m else 0.,trades=m['trades'] if m else 0))
        if not k:continue
        ts=read(RUNTIME/'traces'/a/f'{k}-year{y}.json')['trades']
        for t in ts:
            t=dict(t,principal=cash,profit=cash*t['return_pct']/100,variant=k,fold=y)
            cash+=t['profit'];trades.append(t)
        returns.append(m['return_pct'])
    m=summary(trades);assert isclose(m['compound_return_pct'],compound(returns),abs_tol=1e-6,rel_tol=1e-9)
    return dict(annual=annual,summary=m)


def audit():
    r=read(DOCS/'results.json');assert r['status']=='completed';details=dict(assets={},tracks={},rankings={});checks=[]
    assert digest((DOCS/'plan.json').read_bytes())==r['provenance']['plan_hash']
    for y in FOLDS:
        c=r['choices'][str(y)];p=f'train{y}';assert c==read(DOCS/f'choices-{y}.json')
        assert c['global_choice']==choose(r['results'],r['plan']['variants'],ASSETS,p)
        for a in ASSETS:assert c['held_asset'][a]==choose(r['results'],r['plan']['variants'],[b for b in ASSETS if b!=a],p)
    for a in ASSETS:
        details['assets'][a]={};raws={tf:read(ROOT/r['data'][a][tf]['path']) for tf in ('4h','1d')}
        raws['15m']=read(ROOT/r['plan']['old_data'][a]['path'])
        for k,ps in r['results'][a].items():
            details['assets'][a][k]={}
            for p,m in ps.items():
                path=RUNTIME/'traces'/a/f'{k}-{p}.json';t=read(path);assert t['provenance']==r['provenance']
                assert t['report']['total_trades']==m['trades']==m['wins']+m['losses']+m['flat']
                assert isclose(compound(x['return_pct'] for x in t['trades']),m['return_pct'],abs_tol=1e-6,rel_tol=1e-9)
                assert isclose(t['equity'][-1]['equity'],10000*(1+m['return_pct']/100),abs_tol=1e-6,rel_tol=1e-9)
                assert sum(x['losses'] for x in m['exits'].values())==m['losses']
                checks.append(dict(path=path.relative_to(ROOT).as_posix(),hash=digest(path.read_bytes())))
                if p in ('common','full'):
                    lo,hi=map(stamp,t['period']);data=raws[t['timeframe']]
                    months=calendar_returns(t['equity'],data,periods(lo,hi,'month'))
                    boundaries=periods(lo,hi,'anniversary')
                    if boundaries and boundaries[0][1]>lo:boundaries.insert(0,('首段不足一年',lo,boundaries[0][1]))
                    details['assets'][a][k][p]=dict(years=calendar_returns(t['equity'],data,periods(lo,hi,'year')),
                        anniversaries=calendar_returns(t['equity'],data,boundaries),
                        concentration=stress(t['trades'],months),market=calendar_returns(t['equity'],data,[('full',lo,hi)])[0])
        details['tracks'][a]=dict(
            global_choice=track(r,a,{str(y):r['choices'][str(y)]['global_choice']['selected'] for y in FOLDS}),
            held_asset=track(r,a,{str(y):r['choices'][str(y)]['held_asset'][a]['selected'] for y in FOLDS}),
            old=track(r,a,{str(y):'old_ema55' for y in FOLDS}))
        print('AUDIT',a,flush=True)
    ranking=[]
    for k in r['plan']['variants']:
        values={a:r['results'][a][k]['common']['return_pct'] for a in ASSETS};best=max(values,key=values.get)
        ranking.append(dict(key=k,positive=sum(v>0 for v in values.values()),median_return_pct=median(values.values()),
            best_asset=best,median_without_best=median(v for a,v in values.items() if a!=best),positive_without_best=sum(v>0 for a,v in values.items() if a!=best)))
    ranking.sort(key=lambda x:(-x['median_return_pct'],x['key']));details['rankings']['common']=ranking
    for kind in ('global_choice','held_asset','old'):
        vals={a:details['tracks'][a][kind]['summary']['compound_return_pct'] for a in ASSETS};best=max(vals,key=vals.get)
        details['rankings'][kind]=dict(returns=vals,positive=sum(v>0 for v in vals.values()),median_return_pct=median(vals.values()),
            median_without_best=median(v for a,v in vals.items() if a!=best),best_asset=best)
    freeze(DOCS/'details.json',details)
    freeze(DOCS/'verification.json',dict(status='passed',traces_checked=len(checks),selection_reproduced=True,manifest=checks))
    print('VERIFIED',len(checks),'traces and all chronological/held-asset choices',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','fetch','run','audit']);p.add_argument('--workers',type=int,default=3);args=p.parse_args()
    {'prepare':prepare,'fetch':lambda:fetch(args.workers),'run':lambda:study(args.workers),'audit':audit}[args.action]()
