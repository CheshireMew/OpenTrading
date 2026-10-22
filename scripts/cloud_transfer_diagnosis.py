"""Fixed-parameter six-asset loss, profit concentration and holding-time audit."""
import argparse
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from math import isclose
from types import SimpleNamespace
from pathlib import Path
import json

from app.domain.local_backtest import simulate, Intent
from app.domain.backtest_history import validate_observed_bars
from app.domain.cloud_trade_attribution import analyze, monthly_relationship, compound
from app.services.local_backtest_strategies import digest, load_strategy
from scripts.alt_cloud_parameter_study import ETH_PARAMETERS, BTC_PARAMETERS
from scripts.btc_cloud_parameter_study import freeze, key
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/cloud-transfer-diagnosis-20260911'
RUNTIME=ROOT/'.opentrading_runtime/cloud-transfer-diagnosis-20260911'
ALT=ROOT/'docs/verification/alt-cloud-transfer-20260911'
SOURCE=ROOT/'strategies/trend_cloud_parameters_v4.py'
ASSETS=['eth','btc','sol','bnb','paxg','zec']
COMMON=['2020-09-10T00:00:00Z','2026-09-10T00:00:00Z']


def direction_strategy(module, allowed):
    def on_bar(context):
        intent=module.on_bar(context)
        if intent and intent.action in ('long','short') and intent.action != allowed:
            return Intent('close',reason='保留原反向平仓；禁止开被排除方向') if context.position else None
        return intent
    return SimpleNamespace(on_bar=on_bar)


def prepare():
    if (DOCS/'plan.json').exists():
        print('Plan already frozen'); return
    data={**read(ROOT/'docs/verification/cloud-cross-asset-20260911/data.json'),**read(ALT/'data.json')}
    configs={'eth_original':ETH_PARAMETERS,'btc_original':BTC_PARAMETERS}
    full={};common={};tests=[]
    for a in ASSETS:
        for label,p in configs.items():
            k=key(p);name=f'{a}__{label}';path=None
            if a in ('sol','bnb','paxg','zec'):
                path=ROOT/f'.opentrading_runtime/alt-cloud-transfer-20260911/traces/{a}/{k}-full.json'
            elif label=='eth_original':
                path=ROOT/f'.opentrading_runtime/cloud-cross-asset-20260911/traces/{a}/joint__{k}-full.json'
            elif a=='btc':
                path=ROOT/f'.opentrading_runtime/btc-cloud-parameters-20260911/traces/{k}-full.json'
            if path:
                assert path.exists()
                full[name]=dict(path=path.relative_to(ROOT).as_posix(),hash=digest(path.read_bytes()),asset=a,config=label)
            else:
                dest=RUNTIME/'traces'/f'{name}-full.json'
                full[name]=dict(path=dest.relative_to(ROOT).as_posix(),asset=a,config=label)
                tests.append(dict(name=f'{name}-full',asset=a,config=label,period=[data[a]['start'],COMMON[1]],direction='both'))
            if data[a]['start']==COMMON[0]: common[name]=full[name]
            else:
                dest=RUNTIME/'traces'/f'{name}-common.json'
                common[name]=dict(path=dest.relative_to(ROOT).as_posix(),asset=a,config=label)
                tests.append(dict(name=f'{name}-common',asset=a,config=label,period=COMMON,direction='both'))
            for direction in ('long','short'):
                tests.append(dict(name=f'{name}-common-{direction}',asset=a,config=label,period=COMMON,direction=direction))
    alt=read(ALT/'results.json');hindsight={}
    for a in ('paxg','zec','sol','bnb'):
        k=alt['rankings'][a]['full'][0]
        path=ROOT/f'.opentrading_runtime/alt-cloud-transfer-20260911/traces/{a}/{k}-full.json'
        hindsight[a]=dict(path=path.relative_to(ROOT).as_posix(),hash=digest(path.read_bytes()),asset=a)
    plan=dict(created_at=datetime.now(timezone.utc).isoformat(),assets=ASSETS,data=data,configs=configs,
        full=full,common=common,hindsight=hindsight,tests=tests,common_period=COMMON,
        source_hash=digest(SOURCE.read_bytes()),engine_hash=digest((ROOT/'app/domain/local_backtest.py').read_bytes()),
        purpose='Diagnose existing results, including long/short, years, profit concentration, duration, scale mismatch and correlated market episodes. No parameter search.',
        primary='The two previously fixed original configurations on all six assets, with both full histories and the same six-year period. Hindsight asset winners shown separately only to explain the prior table.',
        interventions='Exactly 24 direction-only six-year diagnostic reruns (six assets x two fixed parameter sets x long-only/short-only). Opposite signals still exit. Compare trade timing/returns with the corresponding side of the unchanged both-side trace. These are explanatory interventions, not newly selected strategies.',
        features='Pre-entry completed-candle width%, prior96-bar efficiency (<.1/.1-.25/>.25), prior30-day return (<-10%/-10..10%/>10%), signal candle body fraction (<1/3,1/3..2/3,>2/3), relative volume (<1/1..2/>2). Prespecified descriptive bins, no threshold optimization, no future entry data.',
        concentration='Trade groups use equal-principal return sums and exact additive log growth, with compounded side-only returns stated separately. Remove top10/top1%/top5% winners and top1/top3 months arithmetically, no retimed entries. Losing/winning month correlation and top10 overlap use the common six years.',
        years='Calendar years from marked account equity; 2020/2026 or first/last years partial. Also retain Sep10 anniversary years. No forced annual liquidation. Side trade groups by close year can differ from marked year returns across the boundary.',
        cautions='All descriptive associations are hindsight; observed holding duration is not an available entry filter. Intrabar exit duration is rounded to candle start (actual may be up to15min longer). Recorded profit peak excludes unknown extrema after an intrabar exit. Market OHLC gaps retained, no invented bars. Monthly correlations are not independent cross-asset validation. No fees/slippage/leverage; current equity reinvested as requested.',
        fixed_grid_support='Retain last study all64 profitable counts; no new parameter combinations.',
        scope='No live trades, downloads, changed original source or engine, no newly chosen stop/entry rule.')
    freeze(DOCS/'plan.json',plan)
    snapshot('039-frozen-transfer-diagnosis',[DOCS/'plan.json',SOURCE,ROOT/'app/domain/local_backtest.py',
        ROOT/'app/domain/cloud_trade_attribution.py',Path(__file__)])
    print(f'Frozen {len(tests)} necessary same-period/direction reruns; no parameter search.',flush=True)


def run_one(task):
    plan=read(DOCS/'plan.json');dest=RUNTIME/'traces'/f"{task['name']}.json"
    if dest.exists():return task['name'],'saved'
    assert digest(SOURCE.read_bytes())==plan['source_hash']
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==plan['engine_hash']
    a=task['asset'];record=plan['data'][a];raw=(ROOT/record['path']).read_bytes()
    assert digest(raw)==record['data_hash'];rows=json.loads(raw)
    times=[r[0] for r in rows];start,end=map(stamp,task['period'])
    i,j=bisect_left(times,start),bisect_left(times,end)
    bars,_=validate_observed_bars(rows[i-650:j],start,end,900000,650,stamp(COMMON[1]))
    module,_=load_strategy(SOURCE)
    strategy=module if task['direction']=='both' else direction_strategy(module,task['direction'])
    p=plan['configs'][task['config']]
    result=simulate(bars,strategy,p,warmup=650,step_ms=900000,initial_cash=10000,position_pct=100)
    out={f:result[f] for f in ('report','trades','signals')}
    out['equity']=[dict(timestamp=x['timestamp'],equity=x['equity']) for x in result['equity']]
    out.update(parameters=p,period=task['period'],direction=task['direction'],task=task,
        provenance=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),data_hash=record['data_hash'],
                        source_hash=plan['source_hash'],engine_hash=plan['engine_hash'],runner_hash=digest(Path(__file__).read_bytes())))
    save(dest,out)
    return task['name'],result['report']['return_pct']


def calculate(workers):
    plan=read(DOCS/'plan.json')
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n,job in enumerate(as_completed([pool.submit(run_one,t) for t in plan['tests']]),1):
            name,value=job.result();print(f'{n}/{len(plan["tests"])} {name}: {value}',flush=True)


def audit():
    plan=read(DOCS/'plan.json');rows={};checks=[];cache={};out=dict(full={},common={},hindsight={})
    for a,info in plan['data'].items():
        raw=(ROOT/info['path']).read_bytes();assert digest(raw)==info['data_hash'];rows[a]=json.loads(raw)
    def inspect(info):
        path=ROOT/info['path'];raw=path.read_bytes();sha=digest(raw)
        if 'hash' in info: assert sha==info['hash']
        if info['path'] in cache:return cache[info['path']]
        trace=json.loads(raw)
        assert trace['provenance']['source_hash']==plan['source_hash'] if 'source_hash' in trace['provenance'] else True
        result=analyze(trace,rows[info['asset']]);cache[info['path']]=result
        checks.append(dict(path=info['path'],sha256=sha,trades=len(trace['trades'])))
        print('ANALYZED',info['asset'],info.get('config','hindsight'),trace['period'],flush=True)
        return result
    for kind in out:
        for name,info in plan[kind].items():out[kind][name]=inspect(info)
    directions={}
    for name,info in plan['common'].items():
        trace=read(ROOT/info['path']);directions[name]={}
        for side in ('long','short'):
            path=RUNTIME/'traces'/f'{name}-common-{side}.json';one=read(path)
            original=[t for t in trace['trades'] if t['side']==side]
            assert len(original)==len(one['trades'])
            for x,y in zip(original,one['trades']):
                for k in ('side','entry_time','exit_time','entry_price','exit_price'):assert x[k]==y[k],(name,side,k)
                assert isclose(x['return_pct'],y['return_pct'],abs_tol=1e-10)
            expected=compound(t['return_pct'] for t in original)
            assert isclose(one['report']['return_pct'],expected,abs_tol=1e-6,rel_tol=1e-9)
            directions[name][side]=dict(return_pct=expected,trades=len(original),report=one['report'],
                                        matched_original_side_trades=True,path=path.relative_to(ROOT).as_posix())
            checks.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path.read_bytes()),trades=len(original)))
    relationships={}
    for config in plan['configs']:
        relationships[config]={}
        for i,a in enumerate(ASSETS):
            for b in ASSETS[i+1:]:
                relationships[config][f'{a}__{b}']=monthly_relationship(out['common'][f'{a}__{config}'],out['common'][f'{b}__{config}'])
    selected={'eth':'eth_original','btc':'btc_original','sol':'eth_original','bnb':'btc_original'}
    combined={}
    for a,c in selected.items():
        for m in out['common'][f'{a}__{c}']['months']:
            combined[m['label']]=combined.get(m['label'],0)+__import__('math').log1p(m['return_pct']/100)
    top_shared=sorted(combined,key=combined.get,reverse=True)[:3]
    shared_stress={a:compound(m['return_pct'] for m in out['common'][f'{a}__{c}']['months'] if m['label'] not in top_shared) for a,c in selected.items()}
    result=dict(plan=plan,**out,direction_reruns=directions,relationships=relationships,
                shared_episode_check=dict(configs=selected,top_three_months=top_shared,return_if_these_months_zero_pct=shared_stress),
                verification=dict(status='passed',traces_checked=len(checks),calendar_reconciled=True,direction_replays_matched=True,manifest=checks))
    freeze(DOCS/'results.json',result);freeze(DOCS/'verification.json',result['verification'])
    print('AUDIT PASSED',len(checks),'trace inputs',flush=True)
    for a in ASSETS:
        d=out['full'][f'{a}__eth_original']
        print(a,'return',d['summary']['compound_return_pct'],'long',d['side'].get('long',{}).get('compound_return_pct'),'short',d['side'].get('short',{}).get('compound_return_pct'),'hours',d['summary']['median_hours'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run','audit']);parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='run':calculate(args.workers)
    else:audit()
