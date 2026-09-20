"""Frozen short-lookback study using Heimdall data, strategy and simulator.

24 candidates; 4 trailing windows x3 update frequencies. Cached causal candidate
paths supply past-only scores. Choices are frozen before policy simulation.
Unchanged choices preserve positions; changes liquidate at the next actual open.
"""
import argparse
from bisect import bisect_left, bisect_right
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import product
from math import isclose, log
from pathlib import Path
import json
import numpy as np

from app.domain.local_backtest import Bar
from app.domain.cloud_window_research_v1 import simulate
from app.domain.cloud_trade_attribution import summary, compound, calendar_returns, periods
from app.services.local_backtest_strategies import load_strategy, validate_parameters, digest
from strategies.trend_cloud_parameters_v4 import Calculation
from scripts.cloud_walkforward_study import read_zip, write_zip, STEPS, SOURCE, WARMUP
from scripts.btc_cloud_parameter_study import BASE, freeze
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/cloud-short-window-20260912'
RUNTIME=ROOT/'.heimdall_runtime/cloud-short-window-20260912'
OLD=ROOT/'docs/verification/cloud-walkforward-20260911'
ASSETS=('paxg','zec','eth','btc')
TFS=('5m','15m','30m','1h')
WEEK=7*86400000
START='2020-12-28T00:00:00Z'
END='2026-09-10T00:00:00Z'
SPLIT='2024-09-09T00:00:00Z'
MIN_TRADES=20


def iso(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def cid(tf,n,x):return f'{tf}__c{n}_t{x:g}_s1__g50__r0'.replace('.','p')
def policy_id(w,u):return f'look{w}w_update{u}w'


def candidates():
    _,spec=load_strategy(SOURCE)
    return {cid(tf,n,x):dict(timeframe=tf,parameters=validate_parameters(spec,{**BASE,'center_length':n,'trigger_mult':x}))
            for tf,n,x in product(TFS,(34,55,89),(.4,.8))}


def schedule(update,start=None,end=None):
    return list(range(start or stamp(START),end or stamp(END),update*WEEK))


def past_score(trace,lo,hi,step):
    """Only marked equity at completed boundaries and fully completed trades."""
    et=[x['timestamp'] for x in trace['equity']]
    i,j=bisect_right(et,lo)-1,bisect_right(et,hi)-1
    assert i>=0 and et[i]==lo and et[j]==hi
    v0,v1=trace['equity'][i]['equity'],trace['equity'][j]['equity']
    assert v0>0 and v1>0
    closed=sum(t['entry_time']>=lo and t['exit_time']+(0 if t['exit_phase']=='open' else step)<=hi
               for t in trace['trades'])
    return dict(return_pct=100*(v1/v0-1),log_return=log(v1/v0),closed_trades=closed)


def choose(scores,minimum=MIN_TRADES):
    eligible=[k for k,x in scores.items() if x['closed_trades']>=minimum and x['return_pct']>0]
    eligible.sort(key=lambda k:(-scores[k]['log_return'],k))
    return dict(chosen=eligible[0] if eligible else None,eligible=len(eligible))


def merge_choices(decisions,end):
    merged=[]
    for i,d in enumerate(decisions):
        hi=decisions[i+1]['at'] if i+1<len(decisions) else end
        if merged and merged[-1]['chosen']==d['chosen']:
            merged[-1]['end']=hi;merged[-1]['decisions']+=1
        else:merged.append(dict(start=d['at'],end=hi,chosen=d['chosen'],decisions=1))
    return merged


def prepare():
    if (DOCS/'plan.json').exists():print('Plan already frozen');return
    paths=[Path(__file__),ROOT/'app/domain/cloud_window_research_v1.py',ROOT/'app/domain/local_backtest.py',SOURCE,
           ROOT/'strategies/trend_cloud_parameters_v4.py',ROOT/'app/domain/cloud_trade_attribution.py',ROOT/'test/test_cloud_short_window.py']
    plan=dict(assets=ASSETS,candidates=candidates(),lookbacks_weeks=[2,4,8,12],updates_weeks=[1,2,4],
        history_start='2020-10-01T00:00:00Z',start=START,end=END,split=SPLIT,minimum_closed_trades=MIN_TRADES,
        fixed_candidate=cid('1h',55,.4),initial_cash=10000,fees=0,slippage=0,leverage=1,position_pct=100,
        sources={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in paths},
        selection='At UTC Monday00:00, rank the24 candidates by marked-equity return over the last2/4/8/12 weeks. Require positive return and>=20 complete trades whose entries AND observed exits lie within that past window. Ties by candidateID. If none qualifies, choose cash.20 is a fixed screening guard, not a significance claim; do not optimize this threshold.',
        windows='All12 schedules start2020-12-28, after a common12-week observation history. Updates every1/2/4 weeks. Test end2026-09-10 is partial. Includes nearly6 calendar years of source history, with5years8months of post-observation testing, never called6 full years of tradable returns.',
        transitions='Adjacent identical choices are merged: positions, trailing protection and pending crossover survive scheduled reviews. If choice changes, old pending order is cancelled and any holding liquidated at the boundary actual open. The new setup waits for its own first completed candle/new crossover. Cash has no position. No synthetic entry merely because current price is beyond a band. Native timeframe stop/protection timing is preserved. Final end closes at last close.',
        indicator_state='EMA center and width use the same continuous causal history as cached candidates. On each activation, seed the strategy before650 warmup bars with the exact preceding indicator state. No future bars enter indicator seeds.',
        scores='Use candidate marked equity, including an existing past-origin position, at exact past window boundaries. Minimum trade count includes only round trips that started and ended within window. Full historical candidate caches can be reused, but only these past scores enter the selector. All decisions frozen before simulated policy outcomes are read.',
        controls='Fixed originalETH hourly settings on identical start/end, no forced periodic liquidation. Only timeframe, EMA34/55/89 and trigger.4/.8 vary. Width31, chase2, initialstop1%, activation2%,giveback50%, ATRoff, reverse1 are fixed.',
        validation='Compare all12 policies on full history, clearly label retrospective winner. Separately use only equity growth up to2024-09-09 to lock one window/update policy per asset, then report its later two-year marked-equity growth. Policy simulation may cache later paths but the method selector receives only early metrics. No future winner substitution. Historical data already examined, not an untouched holdout.',
        retention='Reuse old96 candidate traces and16 native datasets by checked hash. Preserve all original files. Save decisions, segment trades/signals/native equity, complete policy trades/equity, annual and split returns, verification, report and numbered snapshots.')
    freeze(DOCS/'plan.json',plan)
    snapshot('066-frozen-short-window-study',[*paths,DOCS/'plan.json'])
    print('FROZEN4assets,24candidates,12window/update methods',flush=True)


def check_sources():
    p=read(DOCS/'plan.json')
    for f,h in p['sources'].items():assert digest((ROOT/f).read_bytes())==h,f
    return p


def lock():
    plan=check_sources();old_data=read(OLD/'data.json');old_training=read(OLD/'training.json')
    data={};ledger={};manifest=[];count=0
    dates=schedule(1);needed=set(dates+[stamp(END),stamp(SPLIT)])
    for d in dates:
        for w in plan['lookbacks_weeks']:needed.add(d-w*WEEK)
    for a in ASSETS:
        data[a]={};scores={str(w):{str(t):{} for t in dates} for w in plan['lookbacks_weeks']}
        for tf in TFS:
            x=old_data[a][tf];path=ROOT/x['path'];assert digest(path.read_bytes())==x['data_hash']
            rows=read(path);times=[int(b[0]) for b in rows]
            # Check all score and switching boundaries before any outcome is run.
            for t in needed:
                j=bisect_left(times,t)
                assert j>=WARMUP and times[j-1]+STEPS[tf]==t,(a,tf,iso(t))
                if t!=stamp(END):assert times[j]==t,(a,tf,iso(t))
            data[a][tf]=dict(path=x['path'],data_hash=x['data_hash'],source_start=x['start'])
        for ident,variant in plan['candidates'].items():
            rec=old_training[a][ident];path=ROOT/rec['trace_path'];assert digest(path.read_bytes())==rec['trace_hash']
            trace=read_zip(path);assert trace['parameters']==variant['parameters'] and trace['price_cap_pct']==0
            assert trace['data_hash']==data[a][variant['timeframe']]['data_hash']
            et=[e['timestamp'] for e in trace['equity']];ev=[e['equity'] for e in trace['equity']]
            entries=[t['entry_time'] for t in trace['trades']]
            exits=[t['exit_time']+(0 if t['exit_phase']=='open' else STEPS[variant['timeframe']]) for t in trace['trades']]
            assert entries==sorted(entries) and exits==sorted(exits)
            for w in plan['lookbacks_weeks']:
                for t in dates:
                    lo=t-w*WEEK;i,j=bisect_right(et,lo)-1,bisect_right(et,t)-1
                    assert et[i]==lo and et[j]==t
                    n=max(0,bisect_right(exits,t)-bisect_left(entries,lo))
                    scores[str(w)][str(t)][ident]=dict(return_pct=100*(ev[j]/ev[i]-1),log_return=log(ev[j]/ev[i]),closed_trades=n)
                # Independently verify optimized counting against full trade predicate.
                for t in (dates[0],dates[len(dates)//2],dates[-1]):
                    assert scores[str(w)][str(t)][ident]==past_score(trace,t-w*WEEK,t,STEPS[variant['timeframe']])
            manifest.append(dict(asset=a,candidate=ident,path=rec['trace_path'],sha256=rec['trace_hash']))
            count+=1
        freeze(DOCS/f'past-scores-{a}.json',scores)
        ledger[a]={}
        for w,u in product(plan['lookbacks_weeks'],plan['updates_weeks']):
            decisions=[]
            for t in schedule(u):
                past=scores[str(w)][str(t)];s=choose(past)
                decisions.append(dict(at=t,history_start=t-w*WEEK,**s,selected_past=past[s['chosen']] if s['chosen'] else None))
            ledger[a][policy_id(w,u)]=dict(lookback_weeks=w,update_weeks=u,decisions=decisions)
        print('PAST SCORES LOCKED',a,'24 candidates, no subsequent returns',flush=True)
    freeze(DOCS/'data.json',data)
    freeze(DOCS/'selection-lock.json',dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),ledger=ledger,candidate_manifest=manifest))
    print('LOCKED',count,'candidate histories and all weekly choices',flush=True)


def seed_arrays(bars,params):
    bases=np.empty(len(bars));widths=np.empty(len(bars));c=Calculation(params)
    for i,b in enumerate(bars):c.update(b,decisions=False);bases[i]=c.base;widths[i]=c.width
    return bases,widths


def seeded_module(params,tf,bars,first,bases,widths):
    module,_=load_strategy(SOURCE)
    if first:
        c=module.Calculation(params,step_ms=STEPS[tf]);b=bars[first-1]
        c.base=float(bases[first-1]);c.width=float(widths[first-1]);c.pc=b.close
        c.upper=c.base+params['trigger_mult']*c.width;c.lower=c.base-params['trigger_mult']*c.width
        c.previous_close=b.close
        module._calculation=c
    return module


def summarize_policy(trades,eq,rows,segments,decisions):
    m=summary(trades);ret=100*(eq[-1]['equity']/eq[0]['equity']-1)
    assert isclose(compound(t['return_pct'] for t in trades),ret,abs_tol=1e-6,rel_tol=1e-9)
    values=np.array([x['equity'] for x in eq]);m.update(return_pct=ret,final_equity=float(values[-1]),
        max_drawdown_pct=100*float(np.max(1-values/np.maximum.accumulate(values))),
        parameter_changes=max(0,len(segments)-1),reviews=len(decisions),
        cash_days=sum((s['end']-s['start'])/86400000 for s in segments if s['chosen'] is None))
    years=calendar_returns(eq,rows,periods(stamp(START),stamp(END),'year'))
    ts=[x['timestamp'] for x in eq];cut=stamp(SPLIT);i=bisect_right(ts,cut)-1
    assert ts[i]==cut
    split_equity=eq[i]['equity'];m.update(early_return_pct=100*(split_equity/10000-1),later_return_pct=100*(values[-1]/split_equity-1))
    later=values[i:];m['later_max_drawdown_pct']=100*float(np.max(1-later/np.maximum.accumulate(later)))
    months=calendar_returns(eq,rows,periods(stamp(START),stamp(END),'month'))
    m['positive_months']=sum(x['return_pct']>0 for x in months);m['negative_months']=sum(x['return_pct']<0 for x in months)
    by_tf={tf:summary([t for t in trades if t['configuration'].startswith(tf+'__')]) for tf in TFS}
    usage={tf:sum((s['end']-s['start'])/86400000 for s in segments if s['chosen'] and s['chosen'].startswith(tf+'__')) for tf in TFS}
    exits={why:summary([t for t in trades if t['exit_reason']==why]) for why in sorted({t['exit_reason'] for t in trades})}
    stride=max(1,len(eq)//500);curve=eq[::stride]
    if curve[-1]!=eq[-1]:curve.append(eq[-1])
    return dict(metrics=m,years=years,months=months,timeframe_days=usage,by_timeframe=by_tf,exits=exits,curve=curve)


def asset_task(a):
    plan=check_sources();locked=read(DOCS/'selection-lock.json');data=read(DOCS/'data.json')[a]
    lock_hash=digest((DOCS/'selection-lock.json').read_bytes())
    loaded={};arrays={};reports={};lo0=stamp('2020-10-01T00:00:00Z');hi=stamp(END)
    for tf in TFS:
        rows=read(ROOT/data[tf]['path']);times=[int(r[0]) for r in rows]
        i,j=bisect_left(times,lo0)-WARMUP,bisect_left(times,hi)
        bars=[Bar(int(t),float(o),float(h),float(l),float(c),float(v)) for t,o,h,l,c,v in rows[i:j]]
        loaded[tf]=dict(bars=bars,times=[b.timestamp for b in bars],rows=rows)
        for n in (34,55,89):arrays[tf,n]=seed_arrays(bars,{**BASE,'center_length':n})
    policies={**locked['ledger'][a],'fixed':dict(lookback_weeks=None,update_weeks=None,decisions=[dict(at=stamp(START),chosen=plan['fixed_candidate'])])}
    for name,p in policies.items():
        out=DOCS/'policy-reports'/a/f'{name}.json'
        if out.exists():reports[name]=read(out);continue
        segments=merge_choices(p['decisions'],hi);cash=10000.;eq=[];trades=[];segment_records=[]
        for seg in segments:
            ident=seg['chosen'];lo,end=seg['start'],seg['end'];scale=cash/10000
            if ident:
                cp=plan['candidates'][ident];tf=cp['timeframe'];params=cp['parameters'];z=loaded[tf]
                path=RUNTIME/'segments'/a/f'{lo}-{end}__{ident}.json.gz'
                if path.exists():trace=read_zip(path)
                else:
                    i,j=bisect_left(z['times'],lo),bisect_left(z['times'],end);first=i-WARMUP
                    bases,widths=arrays[tf,params['center_length']]
                    module=seeded_module(params,tf,z['bars'],first,bases,widths)
                    trace=simulate(z['bars'][first:j],module,params,warmup=WARMUP,step_ms=STEPS[tf],
                        transition_bar=z['bars'][j] if end<hi else None)
                    trace.pop('fills',None);trace.pop('levels',None)
                    trace.update(configuration=ident,start=lo,end=end,selection_lock_hash=lock_hash)
                    write_zip(path,trace)
                assert trace['selection_lock_hash']==lock_hash
                assert isclose(compound(t['return_pct'] for t in trace['trades']),trace['report']['return_pct'],abs_tol=1e-7,rel_tol=1e-9)
                for t in trace['trades']:
                    trades.append({**t,'trade_id':len(trades)+1,'configuration':ident,'principal':t['principal']*scale,'profit':t['profit']*scale,'quantity':t['quantity']*scale})
                curve=[dict(timestamp=e['timestamp'],equity=e['equity']*scale) for e in trace['equity']]
                cash=trace['report']['final_equity']*scale
                rec={**seg,'return_pct':trace['report']['return_pct'],'trades':len(trace['trades']),'trace_path':path.relative_to(ROOT).as_posix(),'sha256':digest(path.read_bytes())}
            else:
                # Daily points make calendar boundaries exact even during prolonged cash.
                curve=[dict(timestamp=t,equity=cash) for t in range(lo,end,86400000)]+[dict(timestamp=end,equity=cash)]
                rec={**seg,'return_pct':0.,'trades':0}
            if eq and eq[-1]['timestamp']==curve[0]['timestamp']:
                assert isclose(eq[-1]['equity'],curve[0]['equity'],abs_tol=1e-7,rel_tol=1e-9);curve=curve[1:]
            eq.extend(curve);segment_records.append(rec)
        result=summarize_policy(trades,eq,loaded['1h']['rows'],segments,p['decisions'])
        pp=RUNTIME/'policies'/a/f'{name}.json.gz'
        record=dict(asset=a,policy=name,trades=trades,equity=eq,segments=segment_records,decisions=p['decisions'],summary=result)
        if pp.exists():assert read_zip(pp)==record
        else:write_zip(pp,record)
        result.update(asset=a,policy=name,lookback_weeks=p['lookback_weeks'],update_weeks=p['update_weeks'],
            segments=segment_records,decisions=p['decisions'],trace_path=pp.relative_to(ROOT).as_posix(),sha256=digest(pp.read_bytes()))
        freeze(out,result);reports[name]=result
        # Deliberately reveal no later or full result before early-method lock.
        print('SIMULATED',a,name,'records saved',flush=True)
    return a,{k:dict(early_return_pct=v['metrics']['early_return_pct'],report_path=(DOCS/'policy-reports'/a/f'{k}.json').relative_to(ROOT).as_posix()) for k,v in reports.items()}


def run(workers):
    check_sources();out=read(DOCS/'early-results.json') if (DOCS/'early-results.json').exists() else {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs=[pool.submit(asset_task,a) for a in ASSETS if a not in out]
        for f in as_completed(jobs):
            a,result=f.result();out[a]=result;save(DOCS/'early-results.json',out)
    print('All policy traces saved; only early selection metrics returned',flush=True)


def lock_method():
    check_sources();early=read(DOCS/'early-results.json');selected={}
    for a,rs in early.items():
        rank=sorted((k for k in rs if k!='fixed'),key=lambda k:(-rs[k]['early_return_pct'],k))
        selected[a]=dict(chosen=rank[0],early_return_pct=rs[rank[0]]['early_return_pct'],ranking=rank)
    assert len(selected)==4
    freeze(DOCS/'method-lock.json',dict(early_results_hash=digest((DOCS/'early-results.json').read_bytes()),split=SPLIT,selections=selected))
    print('Locked one of12methods per asset using only earlier history',flush=True)


def finish():
    plan=check_sources();lock=read(DOCS/'selection-lock.json');methods=read(DOCS/'method-lock.json');out={};manifest=[]
    for a in ASSETS:
        scores=read(DOCS/f'past-scores-{a}.json');out[a]={}
        for w,u in product(plan['lookbacks_weeks'],plan['updates_weeks']):
            name=policy_id(w,u)
            for d in lock['ledger'][a][name]['decisions']:
                actual=choose(scores[str(w)][str(d['at'])]);assert actual=={k:d[k] for k in ('chosen','eligible')}
                assert d['history_start']==d['at']-w*WEEK
        for p in (DOCS/'policy-reports'/a).glob('*.json'):
            r=read(p);assert digest((ROOT/r['trace_path']).read_bytes())==r['sha256'];out[a][r['policy']]=r
            assert isclose((1+r['metrics']['early_return_pct']/100)*(1+r['metrics']['later_return_pct']/100),1+r['metrics']['return_pct']/100,rel_tol=1e-9)
            manifest.append(dict(path=r['trace_path'],sha256=r['sha256']))
        assert len(out[a])==13
        early=read(DOCS/'early-results.json')[a];rank=sorted((k for k in early if k!='fixed'),key=lambda k:(-early[k]['early_return_pct'],k))
        assert methods['selections'][a]['chosen']==rank[0]
    freeze(DOCS/'results.json',dict(status='completed',plan=plan,results=out,method_lock=methods))
    freeze(DOCS/'verification.json',dict(status='passed',candidate_histories=96,policies=52,decisions=sum(len(p['decisions']) for a in lock['ledger'].values() for p in a.values()),
        past_only_selection_recomputed=True,early_only_method_selection_recomputed=True,compound_reconciled=True,manifest=manifest))
    print('VERIFIED52policies and every past-only selection',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','lock','run','lock-method','finish']);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    {'prepare':prepare,'lock':lock,'run':lambda:run(a.workers),'lock-method':lock_method,'finish':finish}[a.action]()
