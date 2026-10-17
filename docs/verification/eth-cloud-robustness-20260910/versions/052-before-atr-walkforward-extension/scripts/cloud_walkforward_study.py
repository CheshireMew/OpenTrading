"""Frozen four-asset walk-forward selection and paired profit-protection study.

Uses native project data, an opt-in copy of the project engine, and immutable
configuration/selection/trace records. No subsequent-period score is accepted
by the selector. Future paths are cached for computation only, never for ranking.
"""
import argparse
from bisect import bisect_left, bisect_right
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import product
from math import log, isclose
from pathlib import Path
from statistics import median
from threading import local
import gzip
import json

from app.domain.backtest_history import validate_observed_bars
from app.domain.cloud_protection_research_v1 import simulate
from app.domain.cloud_trade_attribution import compound, summary, calendar_returns, periods
from app.services.local_backtest_strategies import load_strategy, validate_parameters, digest
from scripts.btc_cloud_parameter_study import BASE, freeze
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save
from scripts.trend_cloud_study import stamp

DOCS = ROOT/'docs/verification/cloud-walkforward-20260911'
RUNTIME = ROOT/'.heimdall_runtime/cloud-walkforward-20260911'
OLD = ROOT/'docs/verification/cloud-timeframe-20260911'
SOURCE = ROOT/'strategies/trend_cloud_timeframe_v6.py'
ENGINE = ROOT/'app/domain/cloud_protection_research_v1.py'
ASSETS = ['paxg','zec','eth','btc']
TFS = ['5m','15m','30m','1h','1d']
STEPS = dict(zip(TFS,[300000,900000,1800000,3600000,86400000]))
START = '2020-10-01T00:00:00Z'
DAILY_START = '2022-10-01T00:00:00Z'
END = '2026-09-10T00:00:00Z'
METHODS = {
    'g50':dict(label='利润回吐50%（原版）',giveback_pct=50.,cap=0.),
    'g35':dict(label='利润回吐35%',giveback_pct=35.,cap=0.),
    'g25':dict(label='利润回吐25%',giveback_pct=25.,cap=0.),
    'g50c5':dict(label='回吐50%＋价格回撤5%上限',giveback_pct=50.,cap=5.),
    'g50c10':dict(label='回吐50%＋价格回撤10%上限',giveback_pct=50.,cap=10.),
}
AXES = dict(center_length=[34,55,89],trigger_mult=[.4,.8],initial_stop_pct=[1.,2.])
WARMUP=650


def date(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def key(p):return f'c{p["center_length"]}_t{p["trigger_mult"]:g}_s{p["initial_stop_pct"]:g}'.replace('.','p')
def identity(tf,k,m):return f'{tf}__{k}__{m}'


def folds():
    cuts=[f'{y}-{m:02}-01T00:00:00Z' for y,m in [(2023,10),(2024,4),(2024,10),(2025,4),(2025,10),(2026,4)]]+[END]
    result=[]
    for i,(lo,hi) in enumerate(zip(cuts,cuts[1:])):
        y,m=int(lo[:4]),int(lo[5:7])
        b=[]
        for j in range(7):
            month=(y-3)*12+(m-1)+j*6
            b.append(f'{month//12}-{month%12+1:02}-01T00:00:00Z')
        assert b[-1]==lo
        result.append(dict(id=f'f{i+1}',start=lo,end=hi,train_start=b[0],training_boundaries=b,
                           pools=['intraday']+(['all5'] if lo>= '2025-10-01' else [])))
    return result


def prepare():
    if (DOCS/'plan.json').exists():print('Plan already frozen');return
    _,spec=load_strategy(SOURCE)
    variants={key(p):validate_parameters(spec,p) for vals in product(*AXES.values())
              for p in [{**BASE,**dict(zip(AXES,vals))}]}
    files=[Path(__file__),ENGINE,SOURCE,ROOT/'strategies/trend_cloud_parameters_v4.py',ROOT/'app/domain/local_backtest.py',ROOT/'app/domain/cloud_trade_attribution.py',ROOT/'test/test_cloud_walkforward.py']
    plan=dict(assets=ASSETS,timeframes=TFS,axes=AXES,variants=variants,methods=METHODS,folds=folds(),
        start=START,daily_start=DAILY_START,end=END,warmup=WARMUP,
        costs=dict(initial_cash=10000,position_pct=100,fees=0,slippage=0,leverage=1),
        sources={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in files},
        total_variants_per_asset=12*5*5,
        fixed_parameters='Width EMA31, anti-chase2 widths, activation2%, reverse confirmation1, EMA(hl2), EMA(high-low), no ATR initial stop. Center34/55/89 x crossing.4/.8 x stop1/2 =12 entries. Same set for all4 assets.',
        methods_rule='All5 methods keep opposite exit and reversal entry rules. Price caps apply only after the same profit activation and use favourable peak/trough price, not entry price. At peak+100%, g50 retains+50%, cap10 retains+80%, cap5 retains+90%. Ratchet on closed candle; new line is live on next observed candle; gaps use actual open.',
        periods_rule='Intraday pool5m/15m/30m/1h uses3-year trailing selection, then6-month test, six rounds from2023-10-01 to2026-09-10 (last round partial). All5 adds daily on same dates for everyone, only the last2 rounds; PAXG650 daily warmup prevents a full3-year daily training sample earlier. Do not rank totals across unequal pool durations.',
        training_scores='For each exact timeframe/entry/method, compute six consecutive half-year marked-equity log returns in preceding3 calendar years. Candidate paths start flat in2020-10 (daily2022-10), continue causally, and use calendar equity at cutoffs. Training windows can inherit positions initiated earlier, all past. Training trades are exits known by cutoff.',
        robust_selection='Require own3-year return>0 and>=30 closed trades. Neighborhood contains self plus all entries differing in exactly one of the3 axes, same timeframe and protection. Score is median over that neighborhood of each member median six-half-year log return. Require score>0. Rank score, then own median half-year log return, own3-year log return, ID. If none qualifies stay cash. Scores cannot use subsequent half-year results.',
        comparisons='Joint robust selector chooses timeframe,entry,protection. Five method-specific robust selectors choose timeframe/entry with each exit method fixed. A return-only past3-year selector is a diagnostic control. Five paired exit comparisons use the entry/timeframe selected under originalg50. Five fixed originalETH1h entry comparisons never reselect. Shared replays deduplicated.',
        replay='At each scheduled half-year boundary close existing holding at prior candle close and start next segment flat, regardless of whether selection changes; boundary is known in advance. New strategy first sees first test candle at its close, next observed open execution. Same reset for all controls, g50 methods and paired methods. OOS segment10000 normalised, concatenate actual compounded equity and trades; no using future winner.',
        freeze_sequence='Cache causal candidate paths once for computation. Worker returns only prior-window scores, not full returns. Selector accepts only strictly-before-cutoff performance, freezes all fold choices and hashes BEFORE the selected next-segment replays. Full candidate paths are not used to choose hindsight winners or to rewrite choices.',
        interpretation='Historical prices and many related strategies already examined. This is retrospective causal walk-forward evidence, not a genuinely untouched holdout; correlated crypto assets are not four independent experiments. Daily only2 tests, insufficient for a durable optimum. No grid expansion or threshold change after results.',
        retention='Original source/engine/results unchanged; separate opt-in engine. All1200 candidate trade+signal traces and daily/boundary equity compressed onD; configs, source hashes, chronological selection ledgers, each selected replay, verification and report retained.',
        stop_rule='Run this single frozen grid and rule on all4 assets, report failures/stay-cash periods without rescuing with a post-hoc winner. No automatic future schedule or live trading.')
    freeze(DOCS/'plan.json',plan)
    snapshot('052-frozen-four-asset-walkforward',[*files,DOCS/'plan.json'])
    print('FROZEN:4 assets x5 timeframes x12 entries x5 protections;6 intraday folds plus2 all-timeframe folds',flush=True)


_thread=local();_dbs=[]
def init_fetch():
    from app.infra.db import build_database_runtime
    from app.infra.persistence.market.kline_store import KlineStore
    from app.services.market.exchange_gateway import ExchangeGateway
    from app.services.market.market_data_service import MarketDataService
    from config import settings
    db=build_database_runtime(settings);_dbs.append(db)
    _thread.market=MarketDataService(exchange_gateway=ExchangeGateway('binance'),kline_store=KlineStore(database_runtime=db))


def chunk(task):
    a,tf,lo,hi=task;p=RUNTIME/'fetch'/a/tf/f'{lo}-{hi}.json'
    if p.exists():return read(p)
    dt=lambda t:datetime.fromtimestamp(t/1000,timezone.utc)
    rows=_thread.market.load_ohlcv_range(a.upper()+'/USDT',tf,dt(lo),dt(hi-1)).rows
    r=dict(asset=a,timeframe=tf,start=lo,end=hi,rows=[x for x in rows if lo<=x[0]<hi]);freeze(p,r);return r


def fetch(workers):
    if (DOCS/'data.json').exists():print('Data already frozen');return
    old=read(OLD/'data.json');cross=read(ROOT/'docs/verification/cloud-cross-asset-20260911/data.json')
    result={a:{} for a in ASSETS};tasks=[];combined={}
    for a in ASSETS:
        for tf in TFS:
            if a in ('paxg','zec'):result[a][tf]=old[a][tf];continue
            if tf=='15m':
                x=cross[a];result[a][tf]=dict(path=x['path'],data_hash=x['data_hash']);continue
            start=stamp(DAILY_START if tf=='1d' else START)-WARMUP*STEPS[tf]
            combined[a,tf]={}
            for lo in range(start,stamp(END),10000*STEPS[tf]):tasks.append((a,tf,lo,min(stamp(END),lo+10000*STEPS[tf])))
    try:
        with ThreadPoolExecutor(max_workers=workers,initializer=init_fetch) as pool:
            futures=[pool.submit(chunk,t) for t in tasks]
            for n,f in enumerate(as_completed(futures),1):
                x=f.result();combined[x['asset'],x['timeframe']].update({int(r[0]):r for r in x['rows']})
                print('FETCH',n,'/',len(tasks),x['asset'],x['timeframe'],len(x['rows']),flush=True)
    finally:
        for db in _dbs:db.dispose()
    # Recheck each missing interval through the project's live source; preserve genuine gaps.
    init_fetch()
    try:
        for (a,tf),merged in combined.items():
            rows=sorted(merged.values(),key=lambda x:x[0]);step=STEPS[tf];rechecks=[]
            holes=[(int(x[0]+step),int(y[0])) for x,y in zip(rows,rows[1:]) if y[0]>x[0]+step]
            for lo,hi in holes:
                dt=lambda t:datetime.fromtimestamp(t/1000,timezone.utc)
                fresh=_thread.market.load_live_ohlcv_range(a.upper()+'/USDT',tf,dt(lo),dt(hi-1)).rows
                fresh=[x for x in fresh if lo<=x[0]<hi];merged.update({int(x[0]):x for x in fresh});rechecks.append(dict(start=lo,end=hi,returned=len(fresh)))
            rows=sorted(merged.values(),key=lambda x:x[0]);p=RUNTIME/'data'/f'{a}-{tf}.json';freeze(p,rows)
            result[a][tf]=dict(path=p.relative_to(ROOT).as_posix(),data_hash=digest(p.read_bytes()),gap_recheck=rechecks)
    finally:_dbs[-1].dispose()
    for a in ASSETS:
        for tf in TFS:
            x=result[a][tf];p=ROOT/x['path'];assert digest(p.read_bytes())==x['data_hash'];r=read(p)
            lo=stamp(DAILY_START if tf=='1d' else START);hi=stamp(END);times=[b[0] for b in r];i,j=bisect_left(times,lo),bisect_left(times,hi)
            assert times[i]==lo and times[j-1]+STEPS[tf]==hi
            _,g=validate_observed_bars(r[i-WARMUP:j],lo,hi,STEPS[tf],WARMUP,hi)
            result[a][tf]={**x,'start':date(lo),'end':END,'study_rows':j-i,'study_gaps':g,'study_missing':sum(y['missing_bars'] for y in g)}
    freeze(DOCS/'data.json',result)
    print('FROZEN20 native datasets',flush=True)


def write_zip(path,record):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'xt',encoding='utf-8',compresslevel=1) as f:json.dump(record,f,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def read_zip(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)


def run_one(bars,tf,p,cap,lo,hi):
    times=[b.timestamp for b in bars];i,j=bisect_left(times,lo),bisect_left(times,hi)
    assert i>=WARMUP and times[i]==lo and times[j-1]+STEPS[tf]==hi
    module,_=load_strategy(SOURCE)
    return simulate(bars[i-WARMUP:j],module,p,warmup=WARMUP,step_ms=STEPS[tf],peak_price_drawdown_pct=cap)


def score_path(trace,fold):
    eq=trace['equity'];times=[x['timestamp'] for x in eq]
    boundaries=list(map(stamp,fold['training_boundaries']))
    values=[eq[bisect_right(times,b)-1]['equity'] for b in boundaries]
    assert all(v>0 for v in values)
    blocks=[log(b/a) for a,b in zip(values,values[1:])]
    # Exit is known no later than its recorded candle close for close-phase exits.
    count=sum(boundaries[0]<=t['exit_time']+(trace['_step'] if t['exit_phase']=='close' else 0)<boundaries[-1] for t in trace['trades'])
    return dict(half_year_log_returns=blocks,median_half_year_log=median(blocks),
                train_log_return=log(values[-1]/values[0]),training_trades=count,
                training_start=boundaries[0],cutoff=boundaries[-1],return_pct=100*(values[-1]/values[0]-1))


def full_candidate_task(task):
    a,tf=task;plan=read(DOCS/'plan.json');meta=read(DOCS/'data.json')[a][tf]
    rows=read(ROOT/meta['path']);lo=stamp(meta['start']);hi=stamp(END)
    times=[x[0] for x in rows];i,j=bisect_left(times,lo),bisect_left(times,hi)
    bars,_=validate_observed_bars(rows[i-WARMUP:j],lo,hi,STEPS[tf],WARMUP,hi)
    valid_folds=[f for f in plan['folds'] if stamp(f['train_start'])>=lo]
    output={}
    for k,p in plan['variants'].items():
        for m,v in METHODS.items():
            ident=identity(tf,k,m);sp=RUNTIME/'training'/a/f'{ident}.json';tp=RUNTIME/'candidates'/a/f'{ident}.json.gz'
            if sp.exists():assert tp.exists();output[ident]=read(sp);continue
            r=run_one(bars,tf,{**p,'giveback_pct':v['giveback_pct']},v['cap'],lo,hi);r['_step']=STEPS[tf]
            scores={f['id']:score_path(r,f) for f in valid_folds}
            # Native full equity is kept for every replay; candidate path is reduced only
            # after all exact calendar score boundaries and drawdown statistics are computed.
            kept={stamp(d) for f in valid_folds for d in f['training_boundaries']}
            r['equity']=[x for n,x in enumerate(r['equity']) if n==0 or n==len(r['equity'])-1 or x['timestamp']%86400000==0 or x['timestamp'] in kept]
            r.pop('fills',None);r.pop('levels',None);r.pop('_step',None)
            r.update(asset=a,timeframe=tf,entry_key=k,method=m,parameters={**p,'giveback_pct':v['giveback_pct']},price_cap_pct=v['cap'],data_hash=meta['data_hash'],plan_hash=digest((DOCS/'plan.json').read_bytes()))
            write_zip(tp,r)
            record=dict(timeframe=tf,entry_key=k,method=m,scores=scores,trace_path=tp.relative_to(ROOT).as_posix(),trace_hash=digest(tp.read_bytes()))
            freeze(sp,record);output[ident]=record
    return a,tf,output


def check_sources():
    p=read(DOCS/'plan.json')
    for name,h in p['sources'].items():assert digest((ROOT/name).read_bytes())==h,name
    return p


def train(workers):
    plan=check_sources();out=read(DOCS/'training.json') if (DOCS/'training.json').exists() else {a:{} for a in ASSETS}
    tasks=[(a,tf) for a in ASSETS for tf in TFS if sum(v['timeframe']==tf for v in out[a].values())<60]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs=[pool.submit(full_candidate_task,t) for t in tasks]
        for n,j in enumerate(as_completed(jobs),1):
            a,tf,r=j.result();out[a].update(r);save(DOCS/'training.json',out)
            print('TRAIN CACHE',n,'/',len(jobs),a,tf,'60 candidates; no next-segment ranking',flush=True)
    assert all(len(out[a])==300 for a in ASSETS)


def pick(past,variants,mode='robust'):
    """Only records of one predeclared past window are accepted; no future data."""
    ranked=[]
    for ident,x in past.items():
        own=x['score']
        if own['training_trades']<30 or own['train_log_return']<=0:continue
        if mode=='return':score=own['train_log_return'];neighbors=[ident]
        else:
            p=variants[x['entry_key']]
            neighbors=[j for j,y in past.items() if y['timeframe']==x['timeframe'] and y['method']==x['method'] and
                       sum(variants[y['entry_key']][f]!=p[f] for f in AXES)<=1]
            assert len(neighbors)==5
            score=median(past[j]['score']['median_half_year_log'] for j in neighbors)
        if score<=0:continue
        ranked.append(dict(id=ident,score=score,own_median=own['median_half_year_log'],own_log=own['train_log_return'],neighbors=neighbors))
    ranked.sort(key=lambda x:(-x['score'],-x['own_median'],-x['own_log'],x['id']))
    return dict(chosen=ranked[0]['id'] if ranked else None,eligible=len(ranked),ranking=ranked)


def lock():
    p=check_sources();training=read(DOCS/'training.json');ledger={}
    for a in ASSETS:
        ledger[a]={}
        for f in p['folds']:
            for pool in f['pools']:
                past={k:dict(timeframe=v['timeframe'],entry_key=v['entry_key'],method=v['method'],score=v['scores'][f['id']])
                      for k,v in training[a].items() if f['id'] in v['scores'] and (pool=='all5' or v['timeframe']!='1d')}
                assert len(past)==(300 if pool=='all5' else 240)
                assert all(x['score']['cutoff']==stamp(f['start']) and x['score']['training_start']==stamp(f['train_start']) for x in past.values())
                selections={'joint':pick(past,p['variants']),'return_leader':pick(past,p['variants'],'return')}
                for m in METHODS:selections['method_'+m]=pick({k:v for k,v in past.items() if v['method']==m},p['variants'])
                base=selections['method_g50']['chosen'];baseparts=base.split('__') if base else None
                for m in METHODS:
                    selections['paired_'+m]=dict(chosen=identity(baseparts[0],baseparts[1],m) if base else None,entry_selected_using='method_g50')
                    selections['fixed_'+m]=dict(chosen=identity('1h',key(BASE),m),entry_selected_using='originalETH1h_no_selection')
                ledger[a][pool+'_'+f['id']]=dict(fold=f,pool=pool,past=past,selections=selections)
    result=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),training_hash=digest((DOCS/'training.json').read_bytes()),ledger=ledger)
    freeze(DOCS/'selection-lock.json',result)
    print('LOCKED all chronological selections before selected next-segment replay',flush=True)


def replay_task(task):
    a,ident,f=task;tf,k,m=ident.split('__');plan=read(DOCS/'plan.json');meta=read(DOCS/'data.json')[a][tf]
    path=RUNTIME/'replays'/a/f'{f["id"]}__{ident}.json.gz'
    if path.exists():r=read_zip(path)
    else:
        rows=read(ROOT/meta['path']);times=[x[0] for x in rows];lo,hi=stamp(f['start']),stamp(f['end']);i,j=bisect_left(times,lo),bisect_left(times,hi)
        bars,_=validate_observed_bars(rows[i-WARMUP:j],lo,hi,STEPS[tf],WARMUP,stamp(END));v=METHODS[m]
        r=run_one(bars,tf,{**plan['variants'][k],'giveback_pct':v['giveback_pct']},v['cap'],lo,hi)
        r.pop('fills',None);r.pop('levels',None)
        r.update(asset=a,timeframe=tf,entry_key=k,method=m,parameters={**plan['variants'][k],'giveback_pct':v['giveback_pct']},price_cap_pct=v['cap'],period=[f['start'],f['end']],selection_lock_hash=digest((DOCS/'selection-lock.json').read_bytes()))
        write_zip(path,r)
    assert r['selection_lock_hash']==digest((DOCS/'selection-lock.json').read_bytes())
    assert isclose(compound(t['return_pct'] for t in r['trades']),r['report']['return_pct'],abs_tol=1e-7,rel_tol=1e-9)
    return a,ident,f['id'],dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path.read_bytes()),report=r['report'],summary=summary(r['trades']))


def replay(workers):
    check_sources();locked=read(DOCS/'selection-lock.json');tasks={}
    for a,segments in locked['ledger'].items():
        for seg in segments.values():
            for s in seg['selections'].values():
                if s['chosen']:tasks[a,s['chosen'],seg['fold']['id']]=(a,s['chosen'],seg['fold'])
    out=read(DOCS/'replays.json') if (DOCS/'replays.json').exists() else {a:{} for a in ASSETS}
    pending=[t for (a,k,f),t in tasks.items() if f+'__'+k not in out[a]]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs=[pool.submit(replay_task,t) for t in pending]
        for n,j in enumerate(as_completed(jobs),1):
            a,k,f,r=j.result();out[a][f+'__'+k]=r;save(DOCS/'replays.json',out)
            if n%10==0 or n==len(jobs):print('REPLAY',n,'/',len(jobs),flush=True)
    print('REPLAYS COMPLETE',len(tasks),'unique segment/strategy runs',flush=True)


def audit():
    plan=check_sources();data=read(DOCS/'data.json');locked=read(DOCS/'selection-lock.json');replays=read(DOCS/'replays.json');training=read(DOCS/'training.json')
    out={a:{} for a in ASSETS};manifest=[]
    for a in ASSETS:
        for pool in ('intraday','all5'):
            segs=[s for s in locked['ledger'][a].values() if s['pool']==pool]
            result={}
            for policy in segs[0]['selections']:
                cash=10000.;eq=[];trades=[];stages=[]
                for seg in segs:
                    s=seg['selections'][policy];f=seg['fold'];ident=s['chosen'];r=None
                    if ident:
                        rec=replays[a][f['id']+'__'+ident];r=read_zip(ROOT/rec['path'])
                        assert digest((ROOT/rec['path']).read_bytes())==rec['sha256']
                        assert r['report']['total_trades']==len(r['trades'])
                        assert isclose(compound(t['return_pct'] for t in r['trades']),r['report']['return_pct'],abs_tol=1e-7,rel_tol=1e-9)
                        scale=cash/10000
                        for t in r['trades']:trades.append({**t,'principal':t['principal']*scale,'profit':t['profit']*scale,'quantity':t['quantity']*scale,'fold':f['id'],'configuration':ident})
                        curve=[dict(timestamp=x['timestamp'],equity=x['equity']*scale) for x in r['equity']]
                        ret=r['report']['return_pct'];cash=r['report']['final_equity']*scale
                    else:
                        curve=[dict(timestamp=stamp(f['start']),equity=cash),dict(timestamp=stamp(f['end']),equity=cash)];ret=0.
                    if eq and eq[-1]['timestamp']==curve[0]['timestamp']:curve=curve[1:]
                    eq.extend(curve);stages.append(dict(fold=f['id'],start=f['start'],end=f['end'],chosen=ident,return_pct=ret,trades=len(r['trades']) if r else 0,training_return_pct=seg['past'][ident]['score']['return_pct'] if ident else None,eligible=s.get('eligible')))
                assert isclose(compound(t['return_pct'] for t in trades),100*(cash/10000-1),abs_tol=1e-7,rel_tol=1e-9)
                peak=10000.;dd=0
                for x in eq:peak=max(peak,x['equity']);dd=max(dd,100*(1-x['equity']/peak))
                raw=read(ROOT/data[a]['1h']['path'])
                years=calendar_returns(eq,raw,periods(eq[0]['timestamp'],eq[-1]['timestamp'],'year'))
                m=summary(trades);m.update(return_pct=100*(cash/10000-1),final_equity=cash,max_drawdown_pct=dd,positive_segments=sum(s['return_pct']>0 for s in stages),negative_segments=sum(s['return_pct']<0 for s in stages),cash_segments=sum(s['chosen'] is None for s in stages))
                exits={why:summary([t for t in trades if t['exit_reason']==why]) for why in sorted({t['exit_reason'] for t in trades})}
                pp=RUNTIME/'policies'/a/f'{pool}__{policy}.json.gz'
                record=dict(metrics=m,stages=stages,years=years,trades=trades,equity=eq,exits=exits)
                if pp.exists():assert read_zip(pp)==record
                else:write_zip(pp,record)
                stride=max(1,len(eq)//400);curve=eq[::stride]
                if curve[-1]!=eq[-1]:curve.append(eq[-1])
                result[policy]=dict(metrics=m,stages=stages,years=years,exits=exits,curve=curve,trace_path=pp.relative_to(ROOT).as_posix())
                manifest.append(dict(path=pp.relative_to(ROOT).as_posix(),sha256=digest(pp.read_bytes())))
            out[a][pool]=result
    # Recompute every selector from the locked past-only input, and check each cache.
    for a,segs in locked['ledger'].items():
        for seg in segs.values():
            for name,s in seg['selections'].items():
                if name not in ('joint','return_leader') and not name.startswith('method_'):continue
                past=seg['past']
                if name.startswith('method_'):past={k:v for k,v in past.items() if v['method']==name[7:]}
                assert pick(past,plan['variants'],'return' if name=='return_leader' else 'robust')==s
        for k,x in training[a].items():assert digest((ROOT/x['trace_path']).read_bytes())==x['trace_hash']
    freeze(DOCS/'results.json',dict(status='completed',plan=plan,results=out))
    freeze(DOCS/'verification.json',dict(status='passed',candidate_traces=1200,unique_replays=sum(len(x) for x in replays.values()),policy_traces=len(manifest),selection_recomputed_from_past_only=True,compound_and_trade_counts_reconcile=True,manifest=manifest))
    print('VERIFIED1200 candidates, all selections and policy returns',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','fetch','train','lock','replay','audit']);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    {'prepare':prepare,'fetch':lambda:fetch(args.workers),'train':lambda:train(args.workers),'lock':lock,'replay':lambda:replay(args.workers),'audit':audit}[args.action]()
