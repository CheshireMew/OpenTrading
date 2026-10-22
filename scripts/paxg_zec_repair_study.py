"""Bounded parameter-versus-rule experiment; chronological locks and exact traces."""
import argparse
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
from itertools import product
from math import isclose
from pathlib import Path
from statistics import median
import json

from app.domain.local_backtest import simulate
from app.domain.backtest_history import validate_observed_bars
from app.domain.cloud_trade_attribution import summary,compound,calendar_returns,periods,stress
from app.services.local_backtest_strategies import digest,load_strategy,validate_parameters
from scripts.alt_cloud_parameter_study import ETH_PARAMETERS
from scripts.btc_cloud_parameter_study import freeze,key
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT,read,save,paired_entries
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/paxg-zec-repair-20260911'
RUNTIME=ROOT/'.opentrading_runtime/paxg-zec-repair-20260911'
SOURCES={'v4':ROOT/'strategies/trend_cloud_parameters_v4.py','v5':ROOT/'strategies/trend_cloud_atr_confirm_v5.py'}
AXES=dict(center_length=[55,144],trigger_mult=[.4,1.2],chase_mult=[2.,3.],
          activation_pct=None,giveback_pct=[35.,50.],initial_stop_pct=None)
BASE=ETH_PARAMETERS
STEP=900000


def utc():return datetime.now(timezone.utc).isoformat()
def variant_id(p):return key(p)+f"_atr{p.get('atr_stop_mult',0):g}_confirm{p.get('reverse_confirm_bars',1)}".replace('.','p')
def spec(p,atr=0.,confirm=1):
    parameters=p.copy();source='v4'
    if atr or confirm!=1:
        source='v5';parameters.update(atr_length=14,atr_stop_mult=atr,reverse_confirm_bars=confirm)
    return dict(parameters=parameters,source=source)


def grid(asset):
    axes={**AXES,'activation_pct':[.3,2.] if asset=='paxg' else [1.,2.],
                   'initial_stop_pct':[.3,1.] if asset=='paxg' else [1.,3.]}
    variants={}
    for values in product(*axes.values()):
        p={**BASE,**dict(zip(axes,values))};variants[variant_id(p)]=spec(p)
    groups={'entry':[],'exit':[],'joint':list(variants)}
    for k,v in variants.items():
        p=v['parameters']
        if all(p[f]==BASE[f] for f in ['activation_pct','giveback_pct','initial_stop_pct']):groups['entry'].append(k)
        if all(p[f]==BASE[f] for f in ['center_length','trigger_mult','chase_mult']):groups['exit'].append(k)
    return axes,variants,groups


def rank(rows,candidates,period):return sorted(candidates,key=lambda k:(-rows[k][period]['return_pct'],k))


def prepare():
    if (DOCS/'plan.json').exists():print('Frozen plan exists; resume run');return
    data=read(ROOT/'docs/verification/alt-cloud-transfer-20260911/data.json')
    assets={}
    for a in ('paxg','zec'):
        axes,variants,groups=grid(a)
        assert len(variants)==64 and len(groups['entry'])==len(groups['exit'])==8
        first=data[a]['start'];end=data[a]['end']
        assets[a]=dict(data=data[a],axes=axes,variants=variants,groups=groups,baseline=variant_id(BASE),
            periods=dict(train=[first,'2023-09-10T00:00:00Z'],validation=['2023-09-10T00:00:00Z','2024-09-10T00:00:00Z'],
                         final=['2024-09-10T00:00:00Z',end],full=[first,end],
                         y2024=['2024-09-10T00:00:00Z','2025-09-10T00:00:00Z'],y2025=['2025-09-10T00:00:00Z',end]))
    plan=dict(created_at=utc(),assets=assets,source_hashes={k:digest(p.read_bytes()) for k,p in SOURCES.items()},
        engine_hash=digest((ROOT/'app/domain/local_backtest.py').read_bytes()),
        study='Is poor PAXG/ZEC performance parameter mismatch or evidence against the rules in these markets?',
        frozen_parameter_range='64 combinations per asset = 8 entry configurations x8 exit configurations. Center55/144, width31 unchanged, trigger0.4/1.2W, chase2/3W. PAXG activation0.3/2%, initial stop0.3/1%; ZEC activation1/2%, stop1/3%; giveback35/50%. Both directions remain.',
        training='Train all64 on earliest3(PAXG)/4(ZEC) years. Per entry-only/exit-only/joint family take top3 plus baseline. Evaluate this union on next1year. In each family select highest validation return among its frozen top3 and baseline. No expansion.',
        rules='After parameter selection, compare exactly six modes on original parameters AND the selected joint parameters: fixed stop/2ATR14/3ATR14 crossed with opposite confirmation1/2 closes. ATR uses Wilder TR incl previous-close gaps, signal-close ATR distance fixed at entry, never widened; profit protection unchanged. Confirmation affects only opposite-position signals; flat first entries unchanged. Stop/protection always active while waiting; opposite exit preserved even if too far to reverse.',
        final_selection='Only validation ranks the original, entry-only, exit-only, joint, and their specified original/joint method variants. Fix overall validation winner, each anchor method winner, all comparison keys and six one-axis neighbors of joint parameters before reading remaining2years. Neighbor results diagnose fragility, cannot change selections.',
        final='Evaluate every locked comparison+neighbor on full, final2years, each final year. Report all changes versus originals and same-anchor pairs. Do not promote the final-best to a new selected winner. Full-history values are explanatory, not a new optimization.',
        costs=dict(fees=0,slippage=0,leverage=1,initial_cash=10000,position_pct=100),timeframe='15m',warmup=650,
        limitation='All historical years were already examined in prior turns, and range design uses those diagnoses. Last2years are excluded from this round selection only, not a genuinely untouched final dataset. No assertion of eliminating overfitting or exhausting all parameters.',
        stop_rule='One bounded study, no expansion after validation/final. Failed candidates stay visible. Preserve snapshots and every full trade trace.',
        atr_engine_change='Add optional absolute stop-loss distance to project Intent/engine. When absent, legacy output must exactly match original frozen baseline report/trades/signals/equity. Original engine is saved in version041.',
        provenance='Reuse exact project MarketDataService/KlineStore data hashes with650 warmup; observed gaps unchanged. All original files backed up.')
    freeze(DOCS/'plan.json',plan)
    for k,path in SOURCES.items():
        dest=RUNTIME/'sources'/path.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    (RUNTIME/'engine.py').write_bytes((ROOT/'app/domain/local_backtest.py').read_bytes())
    for a,info in assets.items():
        for k,v in info['variants'].items():freeze(RUNTIME/'configs'/a/f'{k}.json',v)
    snapshot('042-frozen-paxg-zec-repair',[DOCS/'plan.json',Path(__file__),*SOURCES.values(),ROOT/'app/domain/local_backtest.py',ROOT/'test/test_cloud_atr_confirmation.py'])
    print('Frozen: 64 parameter sets each + specified ATR/confirmation pairs. Earliest years →1year selection→2years test.',flush=True)


_state=None
def init_worker(plan,provenance):
    global _state
    cache={}
    for a,info in plan['assets'].items():
        data=info['data'];raw=(ROOT/data['path']).read_bytes();assert digest(raw)==data['data_hash']
        rows=json.loads(raw);bars,gaps=validate_observed_bars(rows,stamp(data['start']),stamp(data['end']),STEP,650,stamp(data['end']))
        cache[a]=(rows,bars,[b.timestamp for b in bars])
    _state=plan,provenance,cache


def calculate(task):
    a,k,v,period=task;plan,provenance,cache=_state;info=plan['assets'][a]
    path=RUNTIME/'traces'/a/f'{k}-{period}.json'
    if path.exists():
        old=read(path);assert old['provenance']==provenance and old['parameters']==v['parameters']
        return a,k,period,old['metrics']
    if period in ('final','full','y2024','y2025'):
        lock=read(DOCS/'final-lock.json');assert k in lock['assets'][a]['evaluation_keys']
    rows,bars,times=cache[a];start,end=map(stamp,info['periods'][period])
    i,j=bisect_left(times,start),bisect_left(times,end)
    module,meta=load_strategy(SOURCES[v['source']]);p=validate_parameters(meta,v['parameters'])
    result=simulate(bars[i-650:j],module,p,warmup=650,step_ms=STEP,initial_cash=10000,position_pct=100)
    m=summary(result['trades']);m.update(return_pct=result['report']['return_pct'],max_drawdown_pct=result['report']['max_drawdown_pct'],
        mean_initial_atr_stop_pct=None,exit_reasons={reason:summary([t for t in result['trades'] if t['exit_reason']==reason]) for reason in sorted({t['exit_reason'] for t in result['trades']})})
    assert isclose(m['compound_return_pct'],m['return_pct'],rel_tol=1e-9,abs_tol=1e-7)
    trace={f:result[f] for f in ('report','trades','signals')};trace['equity']=[dict(timestamp=x['timestamp'],equity=x['equity']) for x in result['equity']]
    if k==info['baseline'] and period in ('full','final'):
        old=read(ROOT/f'.opentrading_runtime/alt-cloud-transfer-20260911/traces/{a}/{key(BASE)}-{period}.json')
        for f in ('report','trades','signals','equity'):assert trace[f]==old[f],f'Legacy mismatch {a}/{period}/{f}'
        m['legacy_exact']=True
    trace.update(parameters=v['parameters'],period=info['periods'][period],metrics=m,provenance=provenance,source=v['source'])
    save(path,trace)
    return a,k,period,m


def study(workers):
    plan=read(DOCS/'plan.json');assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==plan['engine_hash']
    assert all(digest(SOURCES[k].read_bytes())==h for k,h in plan['source_hashes'].items())
    provenance=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),source_hashes=plan['source_hashes'],engine_hash=plan['engine_hash'],runner_hash=digest(Path(__file__).read_bytes()))
    dest=DOCS/'results.json';out=read(dest) if dest.exists() else dict(plan=plan,provenance=provenance,
        variants={a:i['variants'].copy() for a,i in plan['assets'].items()},results={a:{} for a in plan['assets']},status='running')
    assert out['provenance']==provenance
    if out['status']=='completed':print('Already complete; no new search.');return
    with ProcessPoolExecutor(max_workers=workers,initializer=init_worker,initargs=(plan,provenance)) as pool:
        def run(stage,requests):
            todo=[(a,k,out['variants'][a][k],p) for a,k,p in requests if p not in out['results'][a].get(k,{})]
            jobs=[pool.submit(calculate,t) for t in todo]
            for n,job in enumerate(as_completed(jobs),1):
                a,k,p,m=job.result();out['results'][a].setdefault(k,{})[p]=m;out['stage']=stage;save(dest,out)
                if n%5==0 or n==len(todo):print(f'{stage} {n}/{len(todo)} {a}/{p} {m["return_pct"]:+.2f}%',flush=True)
        run('parameter-training',[(a,k,'train') for a,i in plan['assets'].items() for k in i['variants']])
        shortlists={a:{g:list(dict.fromkeys(rank(out['results'][a],ks,'train')[:3]+[i['baseline']])) for g,ks in i['groups'].items()} for a,i in plan['assets'].items()}
        freeze(DOCS/'validation-plan.json',dict(shortlists=shortlists,created_by='training_only'))
        run('parameter-validation',[(a,k,'validation') for a,gs in shortlists.items() for k in sorted({x for ks in gs.values() for x in ks})])
        selected={a:{g:rank(out['results'][a],ks,'validation')[0] for g,ks in gs.items()} for a,gs in shortlists.items()}
        freeze(DOCS/'parameter-lock.json',dict(selected=selected,shortlists=shortlists))
        rules={};neighbors={}
        for a,info in plan['assets'].items():
            rules[a]={};base=info['baseline'];joint=selected[a]['joint']
            for label,anchor in [('original',base),('tuned',joint)]:
                rules[a][label]={}
                for atr,confirm in product([0.,2.,3.],[1,2]):
                    v=spec(out['variants'][a][anchor]['parameters'],atr,confirm);k=variant_id(v['parameters'])
                    out['variants'][a][k]=v;freeze(RUNTIME/'configs'/a/f'{k}.json',v)
                    rules[a][label][f'atr{atr:g}_confirm{confirm}']=k
            p=out['variants'][a][joint]['parameters'];ns=[]
            for field,values in info['axes'].items():
                for value in values:
                    if value!=p[field]:ns.append(variant_id({**p,field:value}))
            neighbors[a]=ns
        freeze(DOCS/'methods-plan.json',dict(rules=rules,neighbors=neighbors))
        run('method-validation',[(a,k,p) for a,anchors in rules.items() for k in sorted({k for modes in anchors.values() for k in modes.values()}|set(neighbors[a])) for p in ('train','validation')])
        lock={'assets':{},'provenance':provenance}
        for a,info in plan['assets'].items():
            comparison=list(dict.fromkeys([info['baseline'],*selected[a].values(),*[k for modes in rules[a].values() for k in modes.values()]]))
            lock['assets'][a]=dict(parameter_selected=selected[a],rules=rules[a],
                overall_selected=rank(out['results'][a],comparison,'validation')[0],
                anchor_selected={label:rank(out['results'][a],list(modes.values()),'validation')[0] for label,modes in rules[a].items()},
                comparison_keys=comparison,neighbors=neighbors[a],evaluation_keys=list(dict.fromkeys(comparison+neighbors[a])))
        freeze(DOCS/'final-lock.json',lock)
        print('SELECTIONS LOCKED BEFORE FINAL',json.dumps({a:v['overall_selected'] for a,v in lock['assets'].items()}),flush=True)
        run('final-evaluation',[(a,k,p) for a,v in lock['assets'].items() for k in v['evaluation_keys'] for p in ('final','full','y2024','y2025')])
    out['selection']=lock;out['simulations']=sum(len(v) for rs in out['results'].values() for v in rs.values())
    out.update(status='completed',completed_at=utc());save(dest,out)
    print('COMPLETE',out['simulations'],'period simulations. No final-based changes.',flush=True)


def audit():
    r=read(DOCS/'results.json');assert r['status']=='completed';details={};checks=[]
    for a,info in r['plan']['assets'].items():
        data=read(ROOT/info['data']['path']);details[a]=dict(periods={},pairs={})
        for k,ps in r['results'][a].items():
            for period,m in ps.items():
                path=RUNTIME/'traces'/a/f'{k}-{period}.json';t=read(path);assert t['provenance']==r['provenance']
                assert t['report']['total_trades']==m['trades']==m['wins']+m['losses']+m['flat']
                assert isclose(compound(x['return_pct'] for x in t['trades']),m['return_pct'],abs_tol=1e-6,rel_tol=1e-9)
                checks.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path.read_bytes())))
                if period=='full':
                    start,end=map(stamp,t['period']);annual=calendar_returns(t['equity'],data,periods(start,end,'year'))
                    months=calendar_returns(t['equity'],data,periods(start,end,'month'))
                    details[a]['periods'][k]=dict(years=annual,side={s:summary([x for x in t['trades'] if x['side']==s]) for s in ('long','short')},stress=stress(t['trades'],months))
        sel=r['selection']['assets'][a]
        for label,modes in sel['rules'].items():
            anchor=modes['atr0_confirm1'];base=read(RUNTIME/'traces'/a/f'{anchor}-final.json')
            details[a]['pairs'][label]={}
            for mode,k in modes.items():
                target=read(RUNTIME/'traces'/a/f'{k}-final.json')
                details[a]['pairs'][label][mode]=paired_entries(base,target)
        vals=[r['results'][a][k]['final']['return_pct'] for k in sel['neighbors']]
        details[a]['neighbor_final']=dict(count=len(vals),positive=sum(v>0 for v in vals),median_return_pct=median(vals),minimum=min(vals),maximum=max(vals))
        details[a]['training_positive']={g:sum(r['results'][a][k]['train']['return_pct']>0 for k in keys) for g,keys in info['groups'].items()}
    verification=dict(status='passed',traces_checked=len(checks),baseline_legacy_exact=all(r['results'][a][info['baseline']][p].get('legacy_exact') for a,info in r['plan']['assets'].items() for p in ('full','final')),manifest=checks)
    assert verification['baseline_legacy_exact']
    freeze(DOCS/'details.json',details);freeze(DOCS/'verification.json',verification)
    print('Verified',len(checks),'traces; original baseline outputs remain exactly identical.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run','audit']);parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    {'prepare':prepare,'run':lambda:study(args.workers),'audit':audit}[args.action]()
