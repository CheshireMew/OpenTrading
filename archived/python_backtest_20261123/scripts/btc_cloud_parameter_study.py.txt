"""Bounded BTC parameter search with chronological selection and a locked final test.

Uses the saved MarketDataService data and unchanged OpenTrading simulator. Every
configuration, phase decision and trace is retained; no expansion after final test.
"""
import argparse
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import product
from math import isclose, log1p, expm1
from statistics import median
import json

from app.domain.backtest_history import validate_observed_bars
from app.domain.local_backtest import simulate
from app.services.local_backtest_strategies import digest, load_strategy, validate_parameters, environment
from scripts.cloud_joint_study import gap_sensitivity
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save, metrics
from scripts.trend_cloud_study import stamp

DOCS = ROOT/'docs/verification/btc-cloud-parameters-20260911'
RUNTIME = ROOT/'.opentrading_runtime/btc-cloud-parameters-20260911'
OLD = ROOT/'docs/verification/cloud-cross-asset-20260911'
OLD_RUNTIME = ROOT/'.opentrading_runtime/cloud-cross-asset-20260911'
SOURCE = ROOT/'strategies/trend_cloud_parameters_v4.py'
STEP = 900000
AXES = dict(center_length=[34, 55, 89], width_length=[20, 31, 50],
            trigger_mult=[.4, .8, 1.2], chase_mult=[1.5, 2., 3.],
            activation_pct=[1., 2., 3.], giveback_pct=[35., 50., 65.],
            initial_stop_pct=[.5, 1., 2.])
BASE = dict(center_length=55, width_length=31, trigger_mult=.4, chase_mult=2.,
            activation_pct=2., giveback_pct=50., initial_stop_pct=1.,
            initial_stop_width=0, record_indicators=False)
BASE_OLD_KEY = 'joint__c55_w31_t0p4_d2_a2_g50_s1'


def key(p):
    return '_'.join(f'{a}{p[b]:g}' for a, b in zip(('c','w','t','d','a','g','s'), AXES)).replace('.', 'p')


def balanced_design():
    # 243 distinct combinations. All levels of each axis occur 81 times and
    # every two-axis pairing occurs 27 times; not the full 3**7 grid.
    rows = []
    for a,b,c,d,e in product(range(3), repeat=5):
        indices = (a,b,c,d,e,(a+b+c+d+e)%3,(a+2*b+c+2*d+e)%3)
        rows.append({**BASE, **{f: AXES[f][v] for f,v in zip(AXES,indices)}})
    return rows


def neighbors(p):
    return [{**p, field: value} for field, levels in AXES.items() for value in levels if value != p[field]]


def freeze(path, value):
    if path.exists():
        assert read(path) == value, f'Frozen record differs: {path}'
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            f.write('\n')


def ranking(results, candidates, period):
    return sorted(candidates, key=lambda k: (-results[k][period]['return_pct'], k))


def choose_validation(results, shortlist):
    # No access to final-test or full-period returns in the selection rule.
    return ranking(results, shortlist, 'validation')[0]


def allowed_task(stage, period, candidate, final_lock=None):
    if stage in ('coarse', 'expansion'):
        return period == 'train'
    if stage == 'validation':
        return period == 'validation'
    if stage == 'final':
        return final_lock is not None and candidate in final_lock['evaluation_keys']
    return False


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Plan already frozen; use run to resume')
    data = read(OLD/'data.json')['btc']
    old_plan = read(OLD/'plan.json')
    assert old_plan['variants'][BASE_OLD_KEY]['parameters'] == BASE
    assert digest(SOURCE.read_bytes()) == old_plan['sources']['strategies/trend_cloud_parameters_v4.py']['sha256']
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes()) == old_plan['engine_hash']
    assert digest((ROOT/data['path']).read_bytes()) == data['data_hash']
    params = balanced_design()+[BASE]+neighbors(BASE)
    variants = {key(p): dict(parameters=p) for p in params}
    periods = dict(train=['2018-09-10T00:00:00Z','2022-09-10T00:00:00Z'],
                   validation=['2022-09-10T00:00:00Z','2024-09-10T00:00:00Z'],
                   final=['2024-09-10T00:00:00Z','2026-09-10T00:00:00Z'],
                   full=['2018-09-10T00:00:00Z','2026-09-10T00:00:00Z'])
    periods.update({f'y{y}':[f'{y}-09-10T00:00:00Z',f'{y+1}-09-10T00:00:00Z'] for y in range(2018,2026)})
    plan = dict(created_at=datetime.now(timezone.utc).isoformat(), symbol='BTC/USDT', timeframe='15m',
                axes=AXES, baseline=key(BASE), variants=variants, periods=periods, data=data,
                warmup=650, initial_cash=10000, position_pct=100, fees=0, slippage=0, leverage=1,
                source_hash=digest(SOURCE.read_bytes()), engine_hash=old_plan['engine_hash'],
                design='243 pairwise-balanced joint combinations + baseline and its one-axis alternatives, deduplicated.',
                training='First four years only. Rank coarse set by return. Expand each of top three with all 14 single-axis alternatives within declared levels, once only. Rank all trained versions by training return; freeze top 12.',
                validation='Middle two years. Evaluate top 12, original baseline, and all 14 one-axis neighbors of each top-12 candidate. Only the top 12 may be selected. Pick greatest middle-two-year return, ID tie break. Neighbor results diagnose fragility; they cannot enter the shortlist or change the ranking rule.',
                final='Lock selected candidate before touching last two years. Evaluate only it, baseline and training-return leader. Never promote a final-period winner or adjust a threshold after final results. Then show eight-year and annual descriptive results for these same locked candidates.',
                stop_rule='Stop after this bounded search regardless of final results. No further parameter grid or BTC long-only alteration.',
                assessment='Report final aggregate, both individual final years, comparison with baseline, and validation-neighbor positive fraction/median. No win-rate gate. Passing checks is evidence, not proof against overfitting.',
                leakage_limit='BTC baseline/other historical strategies on 2024-2026 were already examined in this conversation. This is a chronological final test withheld from THIS new parameter selection, not a wholly untouched historical dataset. BTC is also related to ETH.',
                execution='Original v4 entry and exit code; next observed open after close signal; fixed entry-relative stop; opposite signal exit; profit protection updated after close for next bar. 100% current equity reinvested; no fees/slippage/leverage.',
                gaps='Reuse original project MarketDataService/KlineStore snapshot with documented gaps. No interpolated candles. Original observed-bar simulator assumptions retained.',
                environment=environment())
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME/'strategy.py').write_bytes(SOURCE.read_bytes())
    (RUNTIME/'engine.py').write_bytes((ROOT/'app/domain/local_backtest.py').read_bytes())
    freeze(DOCS/'plan.json', plan)
    for k,v in variants.items(): freeze(RUNTIME/'configs'/f'{k}.json',v)
    snapshot('032-frozen-btc-parameter-search', [SOURCE, ROOT/'app/domain/local_backtest.py',
             ROOT/'scripts/btc_cloud_parameter_study.py', ROOT/'test/test_btc_cloud_parameter_study.py', DOCS/'plan.json'])
    print(f'Frozen {len(variants)} initial configurations; chronological 4/2/2 years', flush=True)


_state = None


def init_worker(plan, provenance):
    global _state
    raw=(ROOT/plan['data']['path']).read_bytes()
    assert digest(raw)==plan['data']['data_hash']
    assert digest((RUNTIME/'strategy.py').read_bytes())==plan['source_hash']
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==plan['engine_hash']
    rows=json.loads(raw)
    bars,gaps=validate_observed_bars(rows,stamp(plan['periods']['full'][0]),stamp(plan['periods']['full'][1]),STEP,650,stamp(plan['periods']['full'][1]))
    assert gaps==plan['data']['gaps']
    times=[b.timestamp for b in bars]
    for start,end in plan['periods'].values():
        lo,hi=bisect_left(times,stamp(start)),bisect_left(times,stamp(end))
        validate_observed_bars(rows[lo-650:hi],stamp(start),stamp(end),STEP,650,stamp(plan['periods']['full'][1]))
    _state=(plan,provenance,bars,times)


def calculate(task):
    stage,k,p,periods=task
    plan,provenance,bars,times=_state
    lock=read(DOCS/'final-lock.json') if (DOCS/'final-lock.json').exists() else None
    output={}
    for period in periods:
        assert allowed_task(stage,period,k,lock), f'Unapproved phase: {stage}/{period}/{k}'
        path=RUNTIME/'traces'/f'{k}-{period}.json'
        if path.exists():
            t=read(path)
            assert t['provenance']==provenance and t['parameters']==p and t['period']==plan['periods'][period]
            output[period]=t['metrics']
            continue
        start,end=plan['periods'][period]
        a,b=bisect_left(times,stamp(start)),bisect_left(times,stamp(end))
        module,spec=load_strategy(RUNTIME/'strategy.py')
        result=simulate(bars[a-650:b],module,validate_parameters(spec,p),warmup=650,step_ms=STEP,
                        initial_cash=plan['initial_cash'],position_pct=plan['position_pct'])
        m=metrics(result)
        m.pop('daily_equity',None);m.pop('monthly_returns',None)
        m['gap_sensitivity']=gap_sensitivity(result['trades'],[g for g in plan['data']['gaps'] if stamp(start)<=g['start']<stamp(end)])
        tr={n:result[n] for n in ('report','trades','signals')}
        tr['equity']=[dict(timestamp=x['timestamp'],equity=x['equity']) for x in result['equity']]
        tr.update(metrics=m,parameters=p,period=[start,end],provenance=provenance,phase=stage)
        if k==plan['baseline'] and (period=='full' or period=='final' or period.startswith('y')):
            op='recent' if period=='final' else period
            old=read(OLD_RUNTIME/'traces/btc'/f'{BASE_OLD_KEY}-{op}.json')
            assert all(tr[x]==old[x] for x in ('report','trades','signals','equity'))
            m['original_trace_exact']=op
        n=result['report']['total_trades']
        if n:
            compounded=expm1(sum(log1p(t['return_pct']/100) for t in result['trades']))*100
            assert isclose(compounded,result['report']['return_pct'],rel_tol=1e-9,abs_tol=1e-7)
        save(path,tr)
        output[period]=m
    return k,output


def study(workers):
    plan=read(DOCS/'plan.json')
    provenance=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()), data_hash=plan['data']['data_hash'],
                    source_hash=plan['source_hash'],engine_hash=plan['engine_hash'],
                    runner_hash=digest((ROOT/'scripts/btc_cloud_parameter_study.py').read_bytes()))
    path=DOCS/'results.json'
    out=read(path) if path.exists() else dict(plan=plan,provenance=provenance,variants=plan['variants'].copy(),results={},status='running')
    assert out['provenance']==provenance
    if out['status']=='completed':
        print('Already complete; no additional search',flush=True);return
    def add(ps):
        for p in ps:
            k=key(p);v=dict(parameters=p)
            out['variants'].setdefault(k,v)
            freeze(RUNTIME/'configs'/f'{k}.json',v)
    with ProcessPoolExecutor(max_workers=workers,initializer=init_worker,initargs=(plan,provenance)) as pool:
        def run(stage,keys,periods):
            todo=[k for k in keys if not all(p in out['results'].get(k,{}) for p in periods)]
            jobs=[pool.submit(calculate,(stage,k,out['variants'][k]['parameters'],periods)) for k in todo]
            for i,future in enumerate(as_completed(jobs),1):
                k,values=future.result()
                out['results'].setdefault(k,{}).update(values)
                out['stage']=stage
                save(path,out)
                print(f'{stage} {i}/{len(todo)} {k}: {values[periods[0]]["return_pct"]:+.2f}%',flush=True)
        run('coarse',list(plan['variants']),['train'])
        coarse=ranking(out['results'],plan['variants'],'train')
        expanded={key(p):p for k in coarse[:3] for p in neighbors(out['variants'][k]['parameters'])}
        expansion=dict(coarse_ranking=coarse,training_leaders=coarse[:3],variants=expanded,
                       results_hash=digest(json.dumps({k:out['results'][k]['train'] for k in sorted(plan['variants'])},sort_keys=True).encode()))
        freeze(DOCS/'training-expansion.json',expansion)
        add(expanded.values())
        run('expansion',list(expanded),['train'])
        trained=sorted(set(plan['variants'])|set(expanded))
        train_rank=ranking(out['results'],trained,'train')
        shortlist=train_rank[:12]
        neighborhood={k:[key(p) for p in neighbors(out['variants'][k]['parameters'])] for k in shortlist}
        add(p for k in shortlist for p in neighbors(out['variants'][k]['parameters']))
        validation_keys=sorted(set(shortlist+[plan['baseline']]+[n for ns in neighborhood.values() for n in ns]))
        phase=dict(training_ranking=train_rank,shortlist=shortlist,neighbors=neighborhood,validation_keys=validation_keys)
        freeze(DOCS/'validation-plan.json',phase)
        run('validation',validation_keys,['validation'])
        selected=choose_validation(out['results'],shortlist)
        diagnostics={}
        for k,ns in neighborhood.items():
            values=[out['results'][n]['validation']['return_pct'] for n in ns]
            diagnostics[k]=dict(total=len(values),positive=sum(v>0 for v in values),median_return_pct=median(values),minimum_return_pct=min(values),maximum_return_pct=max(values))
        lock=dict(selected=selected,parameters=out['variants'][selected]['parameters'],
                  training_leader=train_rank[0],shortlist=shortlist,
                  validation_ranking=ranking(out['results'],shortlist,'validation'),
                  evaluation_keys=list(dict.fromkeys([selected,plan['baseline'],train_rank[0]])),
                  neighborhood=diagnostics,provenance=provenance,
                  validation_results_hash=digest(json.dumps({k:out['results'][k]['validation'] for k in validation_keys},sort_keys=True).encode()))
        freeze(DOCS/'final-lock.json',lock)
        print('FINAL SELECTION LOCKED: '+selected,flush=True)
        run('final',lock['evaluation_keys'],list(plan['periods']))
    out['selection']=lock
    out['training_ranking']=train_rank
    out['simulations']=sum(len(v) for v in out['results'].values())
    m=out['results'][selected]
    out['assessment']=dict(final_profitable=m['final']['return_pct']>0,
          both_final_years_profitable=all(m[p]['return_pct']>0 for p in ('y2024','y2025')),
          final_beats_baseline=m['final']['return_pct']>out['results'][plan['baseline']]['final']['return_pct'],
          validation_neighbors_two_thirds_positive=diagnostics[selected]['positive']*3>=diagnostics[selected]['total']*2,
          validation_neighbor_median_positive=diagnostics[selected]['median_return_pct']>0)
    out.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat())
    save(path,out)
    files=sorted((RUNTIME/'traces').glob('*.json'))
    save(DOCS/'trace-manifest.json',dict(traces=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p.read_bytes())) for p in files]))
    print(f'Completed {out["simulations"]} simulations. Locked final return {m["final"]["return_pct"]:+.2f}%; no retuning.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('--workers',type=int,choices=[1,2],default=2)
    args=parser.parse_args()
    prepare() if args.action=='prepare' else study(args.workers)
