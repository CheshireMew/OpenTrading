"""Entry-only investigation with fixed exits, cached project bars and engine v4."""
import argparse
from bisect import bisect_left
from datetime import datetime,timezone
import json

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import Bar,simulate
from app.domain.backtest_diagnostics import summarize
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import digest,environment,load_strategy,validate_parameters
from config import settings
from scripts.cloud_manual_study import BASELINE,entry_frequency,select
from scripts.cloud_robustness_study import ROOT,stitched
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import metrics,read,save
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/eth-cloud-entry-20260910'
RUNTIME=ROOT/'.opentrading_runtime/cloud-entry-20260910'
SOURCE=ROOT/'strategies/trend_cloud_entry_v2.py'
NAMES={
    'baseline':'原入场规则（对照）',
    'aligned_slope':'开仓方向必须与中心线近两小时方向一致',
    'local_trend':'近两小时也要走得顺，净移动至少占 30%',
    'few_crossings':'近四小时穿越中心线不超过两次',
    'strong_close':'突破那根顺向收盘，且收在有利一侧的四分之一',
    'closer_entry':'离中心超过 1.25 倍宽度不追',
    'no_spike':'突破那根振幅不超过先前常见振幅的 1.5 倍',
    'active_market':'近期常见振幅至少占价格 0.25%',
    'structure_break':'收盘还必须突破之前两小时的最高或最低价',
}


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Frozen plan exists; do not replace')
    old=read(ROOT/'docs/verification/eth-cloud-manual-20260910/plan.json')
    plan={k:old[k] for k in ('symbol','timeframe','start','end','warmup','data_hash','periods','initial_cash','position_pct')}
    plan.update(created_at=datetime.now(timezone.utc).isoformat(),
                variants={k:dict(name=v,parameters=dict(entry_filter=k,record_indicators=False)) for k,v in NAMES.items()},
                objective='User correction: investigate whether and when to enter. Profit protection is not the main question. Change only entry filtering; keep original exits.',
                frozen_rules=['EMA(hl2,31) center, EMA(high-low,31) width, raw close crossing center +/-0.8 width, distance <=2 width, eight-hour efficiency >=20%.',
                              'For every candidate, profit protection fixed: activate at 2% favorable movement, allow 50% giveback; raw opposite signal independently exits even when new entry blocked.',
                              'One extra entry condition at a time; no combined filters, threshold sweep, altered stop/target, or delayed opposite exit.',
                              'Features only use signal candle or earlier completed bars; signal at close, trade next open. No current entry-candle high/low.',
                              'strong_close: bullish body and close in top quarter for long; bearish body and close in bottom quarter for short.',
                              'closer_entry: directional close-center distance <=1.25 current widths, versus baseline 2.',
                              'no_spike: signal candle high-low <=1.5 previous completed EMA31 range; do not normalize by a width that already includes the spike.',
                              'active_market: current EMA31 range / signal close >=0.0025.',
                              'structure_break: signal close > highest high of preceding eight bars for long; < lowest low for short. Excludes signal candle from lookback.',
                              'few_crossings: count changes in sign(close-center) over sixteen bars including signal close. Exact equality retains prior nonzero side.',
                              'Quarter tests start flat and force close at quarter end, capital compounds between quarters. Full two-year run is continuous. No costs or leverage.'],
                diagnosis='Annotate every original executed trade with pre-entry features. For each fixed filter show retained/rejected winning and losing counts and mean percentage outcome separately in first year and following year. These subsets are attribution, not complete filtered-strategy returns. Then rerun the actual strategy to include changed holding states.',
                selection='Before later results: require first-year wins > losses, positive total return and >=50 trades. Rank return/drawdown then return then ID. None passing means no selection, never substitute retrospective winner.',
                acceptance='Selected candidate must also have full and following-year wins > losses, following-year positive return and >=50 trades, and at least three quarters with positive return and at least three quarters with wins > losses. Failure does not prove all trend strategies impossible.',
                limit='Only these nine versions, 54 simulations. No adding rules after viewing results. Preserve old studies. Any finding is an association or failure mode, not proof of an economic cause.',
                caveat='All data previously seen; chronological split reduces direct selection leakage but is not untouched out-of-sample. Prior methods and screenshot fitting have already used the same market history.')
    save(DOCS/'plan.json',plan)
    RUNTIME.mkdir(parents=True,exist_ok=True)
    snapshot('014-frozen-entry-only-study',[SOURCE,ROOT/'scripts/cloud_entry_study.py',ROOT/'test/test_cloud_entry.py',DOCS/'plan.json'])
    print('Frozen: nine entry-only versions, 54 simulations, unchanged exits',flush=True)


def annotate(bars,result):
    module,spec=load_strategy(SOURCE)
    c=module.Calculation(validate_parameters(spec,{'record_indicators':False}))
    features=[]
    for bar in bars:
        c.update(bar,decisions=False)
        features.append({s:c.features(d) for s,d in (('long',1),('short',-1))})
    times=[b.timestamp for b in bars]
    annotated=[]
    for t in result['trades']:
        i=bisect_left(times,t['entry_time'])
        assert times[i]==t['entry_time'] and i>32
        f=features[i-1][t['side']]
        annotated.append({**t,'feature_time':times[i-1],'features':f,'filters':module.Calculation.decisions(f)})
    return annotated


def cohort(trades,key):
    keep=[t for t in trades if t['filters'][key]]
    reject=[t for t in trades if not t['filters'][key]]
    base=summarize(trades)
    kept=summarize(keep)
    rejected=summarize(reject)
    return dict(baseline=base,kept=kept,rejected=rejected,
                losing_trades_rejected_pct=rejected['losses']/base['losses']*100 if base['losses'] else None,
                winning_trades_rejected_pct=rejected['wins']/base['wins']*100 if base['wins'] else None,
                note='Original executed trades only. Classification uses pre-entry data, but outcomes are retrospective. Do not compound this subset as the new strategy; changed position states require rerun.')


def study():
    plan=read(DOCS/'plan.json')
    files=[SOURCE,ROOT/'scripts/cloud_entry_study.py',ROOT/'scripts/cloud_manual_study.py',ROOT/'scripts/cloud_robustness_study.py',
           ROOT/'scripts/profit_protection_study.py',ROOT/'scripts/trend_cloud_study.py',ROOT/'app/domain/local_backtest.py',
           ROOT/'app/domain/backtest_diagnostics.py',ROOT/'app/services/local_backtest_strategies.py',DOCS/'plan.json']
    provenance=dict(files={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in files},environment=environment())
    raw=(BASELINE/'data.json').read_bytes()
    assert digest(raw)==plan['data_hash']
    provenance['data_hash']=digest(raw)
    bars=[Bar(int(r[0]),*map(float,r[1:])) for r in json.loads(raw)]
    times=[b.timestamp for b in bars]
    path=DOCS/'results.json'
    output=read(path) if path.exists() else dict(plan=plan,provenance=provenance,results={},status='running')
    assert output['provenance']==provenance

    def calculate(key,period):
        trace_path=RUNTIME/f'{key}-{period}.json'
        if period in output['results'].get(key,{}):
            r=read(trace_path)
            assert r['provenance']==provenance
            return r
        start,end=plan['periods'][period]
        a,b=bisect_left(times,stamp(start)),bisect_left(times,stamp(end))
        assert a>=650 and b-a==(stamp(end)-stamp(start))//900000
        module,spec=load_strategy(SOURCE)
        parameters=validate_parameters(spec,plan['variants'][key]['parameters'])
        r=simulate(bars[a-650:b],module,parameters,warmup=650,step_ms=900000,initial_cash=10000,position_pct=100)
        # Every unchanged-entry baseline must match the previous project study exactly.
        reference=read(ROOT/f'.opentrading_runtime/cloud-manual-20260910/baseline-{period}.json') if key=='baseline' else None
        if reference:
            assert r['trades']==reference['trades'] and r['equity']==reference['equity']
        m=metrics(r)
        m.update(entry_frequency(r['trades'],start,end))
        output['results'].setdefault(key,{})[period]=m
        trace={k:r[k] for k in ('report','trades','signals','equity')}
        trace.update(provenance=provenance,parameters=parameters,period=[start,end])
        save(trace_path,trace)
        save(path,output)
        print(f'{period} {key}: {m["wins"]} wins / {m["losses"]} losses, {m["win_rate"]:.1f}% win rate, {m["return_pct"]:+.2f}% return',flush=True)
        return trace

    for key in NAMES:
        calculate(key,'selection')
    ranking=select({k:v['selection'] for k,v in output['results'].items()})
    choice=dict(ranking=ranking,selected=ranking[0] if ranking else None,provenance=provenance)
    if (DOCS/'selection.json').exists():
        assert read(DOCS/'selection.json')==choice
    else:
        save(DOCS/'selection.json',choice)
    output['selection']=choice
    save(path,output)
    print('LOCKED FIRST YEAR CHOICE: '+str(choice['selected']),flush=True)
    output['following_year']={}
    for key in NAMES:
        joined=stitched([(f'q{i}',calculate(key,f'q{i}')) for i in range(1,5)])
        summary={**joined['report'],**summarize(joined['trades'],include_streak=True)}
        summary.update(entry_frequency(joined['trades'],plan['periods']['q1'][0],plan['periods']['q4'][1]))
        output['following_year'][key]=summary
        save(RUNTIME/f'{key}-following-year.json',joined)
        calculate(key,'full')
    periods={p:annotate(bars,read(RUNTIME/f'baseline-{p}.json')) for p in ('selection','following-year','full')}
    save(RUNTIME/'annotated-baseline.json',periods)
    output['cohorts']={p:{k:cohort(trades,k) for k in NAMES} for p,trades in periods.items()}
    output['acceptance']={}
    for key in NAMES:
        f=output['results'][key]['full']; y=output['following_year'][key]
        q=[output['results'][key][f'q{i}'] for i in range(1,5)]
        checks=dict(full_win_count=f['wins']>f['losses'],following_year_win_count=y['wins']>y['losses'],
                    following_year_profit=y['return_pct']>0,sufficient_trades=y['total_trades']>=50,
                    quarter_profit=sum(m['return_pct']>0 for m in q)>=3,
                    quarter_win_count=sum(m['wins']>m['losses'] for m in q)>=3)
        output['acceptance'][key]=dict(checks=checks,passed=all(checks.values()))
    selected=choice['selected']
    output['accepted_candidate']=selected if selected and output['acceptance'][selected]['passed'] else None
    output['baseline_exact_all_six_periods']=True
    output['status']='completed'
    output['simulations']=sum(len(v) for v in output['results'].values())
    save(path,output)
    print('Complete: '+json.dumps(dict(selected=selected,accepted=output['accepted_candidate'],simulations=output['simulations'])),flush=True)


def publish():
    data=read(DOCS/'results.json')
    assert data['status']=='completed'
    assert data['provenance']['files'][SOURCE.relative_to(ROOT).as_posix()]==digest(SOURCE.read_bytes())
    receipt_path=DOCS/'project-runs.json'
    receipt=read(receipt_path) if receipt_path.exists() else dict(provenance=data['provenance'],runs={})
    assert receipt['provenance']==data['provenance']
    database=build_database_runtime(settings)
    service=LocalBacktestService(database)
    try:
        for key,v in data['plan']['variants'].items():
            if key not in receipt['runs']:
                cmd={k:data['plan'][k] for k in ('symbol','timeframe','start','end','initial_cash','position_pct')}
                cmd.update(strategy='trend_cloud_entry_v2',parameters={**v['parameters'],'record_indicators':True})
                record=service.create(LocalBacktestCommand.model_validate(cmd))
                receipt['runs'][key]=dict(run_id=record['id'],verified=False)
                save(receipt_path,receipt)
            record=service.repository.get(receipt['runs'][key]['run_id'])
            if record['status']=='completed' and not receipt['runs'][key]['verified']:
                actual=read(service.directory(record['id'])/'result.json')
                expected=read(RUNTIME/f'{key}-full.json')
                assert record['metadata']['data_hash']==data['provenance']['data_hash']
                assert actual['report']==expected['report'] and actual['trades']==expected['trades'] and actual['signals']==expected['signals']
                receipt['runs'][key]['verified']=True
                save(receipt_path,receipt)
            print(f'{key}: {record["status"]}, verified={receipt["runs"][key]["verified"]}, {record["id"]}',flush=True)
    finally:
        database.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','publish'])
    args=parser.parse_args()
    {'prepare':prepare,'run':study,'publish':publish}[args.action]()
