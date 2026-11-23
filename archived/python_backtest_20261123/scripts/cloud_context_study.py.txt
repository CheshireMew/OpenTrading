"""Support/resistance, momentum and trend study using existing engine and cached bars."""
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

DOCS=ROOT/'docs/verification/eth-cloud-context-20260910'
RUNTIME=ROOT/'.opentrading_runtime/cloud-context-20260910'
SOURCE=ROOT/'strategies/trend_cloud_context_v3.py'
NAMES={
    'baseline':'原入场规则（对照）',
    'support':'支撑阻力：位置和空间都合适',
    'momentum':'一小时动量支持方向',
    'trend':'四小时趋势支持方向',
    'support_momentum':'支撑阻力＋动量',
    'support_trend':'支撑阻力＋趋势',
    'momentum_trend':'动量＋趋势',
    'all_three':'支撑阻力＋动量＋趋势',
    'support_room':'支撑阻力拆分：只检查前方空间',
    'support_touch':'支撑阻力拆分：只检查入场位置',
}
MASKS=dict(baseline=0,support=1,momentum=2,trend=4,support_momentum=3,support_trend=5,momentum_trend=6,all_three=7,support_room=1,support_touch=1)
CORE=list(NAMES)[:8]


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Frozen plan exists; create a new version for changes')
    old=read(ROOT/'docs/verification/eth-cloud-manual-20260910/plan.json')
    plan={k:old[k] for k in ('symbol','timeframe','start','end','warmup','data_hash','periods','initial_cash','position_pct')}
    variants={k:dict(name=name,selection_eligible=k in CORE,parameters=dict(filter_mask=MASKS[k],
                    support_rule='room' if k=='support_room' else 'touch' if k=='support_touch' else 'both',record_indicators=False)) for k,name in NAMES.items()}
    plan.update(created_at=datetime.now(timezone.utc).isoformat(),variants=variants,
                objective='New user authorization: add support/resistance, momentum and trend to the existing strategy. Primary goal remains winning trades outnumber losing trades with positive return. Compare components separately and jointly.',
                frozen_rules=[
                    'UNCHANGED: EMA(hl2,31) center, EMA(high-low,31) width W, raw close cross center +/-0.8W, distance <=2W, ER32 >=0.2.',
                    'UNCHANGED: activation at 2% favorable movement, 50% giveback OR raw opposite crossing exits. An entry filter never delays opposite exit. No fees, slippage, leverage, initial fixed stop or fixed target.',
                    'UTC aggregation: only complete contiguous 1h, 4h and 24h buckets. Initial partial bucket discarded. Signals at 15m close; fills at next open.',
                    'SR levels: previous completed UTC day high/low and strict hourly pivot highs/lows with two bars on EACH side. Pivot known only after both right-side hours close. Retain pivots for 120h after confirmation.',
                    'Levels must be known at signal candle OPEN. A level first confirmed at that candle CLOSE cannot be used to assert an earlier touch.',
                    'Nearest level at/below current close is support; at/above is resistance. Old highs can become support after crossing, lows can become resistance. Equality gives both.',
                    'SR touch/location: long close strictly above nearest support by <=1W and signal low <=support+0.25W; short mirrored. Original channel crossing remains required.',
                    'SR room: long nearest overhead resistance >=2W away; short nearest lower support >=2W away. No opposing level passes only if some level is known. Not proof of unlimited space.',
                    'Main SR requires touch AND room. Two diagnostic variants isolate touch and room; excluded from choosing a winner.',
                    'Momentum: Wilder RSI14 of completed hourly closes >=55 AND higher than preceding hourly RSI for long; <=45 AND lower for short. An hour closing at signal close is available; no unfinished hour.',
                    'Trend: latest completed four-hour close above SMA20 of four-hour closes, and SMA above its value four completed four-hour bars earlier; short mirrored. 24 completed four-hour closes fit in unchanged 650-bar warmup.',
                    'Eight combinations of three components including baseline. No threshold sweep or changed rule after outcomes.',
                    'Following year is four quarterly runs starting flat, forced flat at end, with compounded capital. Full two-year run is continuous.'],
                diagnosis='Annotate original trades with pre-entry features: fraction of original losses blocked AND winners missed. Classification is not new-strategy return. Rerun all variants and report trade counts, streaks, average win/loss and sides.',
                selection='First-year only, eight core variants only: wins > losses, positive return and >=50 trades, rank return/drawdown then return then ID. Lock before following periods. None passing means no selection.',
                acceptance='Selected version must have more wins than losses in full and following year, following year positive return and >=50 trades, >=3 quarters positive and >=3 quarters with more wins than losses. Diagnostic SR ablations cannot be selected.',
                limit='10 predeclared versions x 6 periods = 60 simulations. Ten additional full-period project records must reproduce results, not independent experiments. No tuning after outcomes.',
                caveat='Both years already used in previous studies; not untouched out-of-sample. These are specific quantified definitions, not all technical analysis or all discretionary trading.')
    save(DOCS/'plan.json',plan)
    RUNTIME.mkdir(parents=True,exist_ok=True)
    snapshot('018-frozen-context-study',[SOURCE,ROOT/'scripts/cloud_context_study.py',ROOT/'test/test_cloud_context.py',DOCS/'plan.json'])
    print('Frozen 10 versions; 60 simulations; exits unchanged',flush=True)


def annotate(bars,result):
    module,spec=load_strategy(SOURCE)
    c=module.Calculation(validate_parameters(spec,{'filter_mask':0,'record_indicators':False}))
    times=[b.timestamp for b in bars]
    wanted={t['entry_time']-900000 for t in result['trades']}
    features={}
    for bar in bars:
        c.update(bar,decisions=False)
        if bar.timestamp in wanted:
            features[bar.timestamp]=c.features
    annotated=[]
    for t in result['trades']:
        i=bisect_left(times,t['entry_time'])
        assert times[i]==t['entry_time'] and i>32
        f=features[times[i-1]][t['side']]
        assert f['levels_known_at'] is None or f['levels_known_at']<=times[i-1]
        assert f['hour_known_at'] is None or f['hour_known_at']<=t['entry_time']
        assert f['four_known_at'] is None or f['four_known_at']<=t['entry_time']
        annotated.append({**t,'feature_time':times[i-1],'features':f,'filters':module.Calculation.choices(f)})
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
    files=[SOURCE,ROOT/'scripts/cloud_context_study.py',ROOT/'scripts/cloud_manual_study.py',ROOT/'scripts/cloud_robustness_study.py',
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
        print(f'{period} {key}: {m["wins"]} wins / {m["losses"]} losses, {(m["win_rate"] or 0):.1f}% win rate, {m["return_pct"]:+.2f}% return',flush=True)
        return trace

    for key in NAMES:
        calculate(key,'selection')
    ranking=select({k:output['results'][k]['selection'] for k in CORE})
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
    # Reset feature calculations with exactly the same warmup as each simulation.
    periods={}
    for period in ('selection','full','q1','q2','q3','q4'):
        start,end=plan['periods'][period]
        a,b=bisect_left(times,stamp(start)),bisect_left(times,stamp(end))
        periods[period]=annotate(bars[a-650:b],read(RUNTIME/f'baseline-{period}.json'))
    features={(p,t['entry_time'],t['side']):t for p in ('q1','q2','q3','q4') for t in periods[p]}
    periods['following-year']=[{**t,**{k:features[(t['fold'],t['entry_time'],t['side'])][k] for k in ('feature_time','features','filters')}}
                               for t in read(RUNTIME/'baseline-following-year.json')['trades']]
    save(RUNTIME/'annotated-baseline.json',periods)
    output['cohorts']={p:{k:cohort(trades,k) for k in NAMES} for p,trades in periods.items()}
    output['side_breakdown']={}
    for key in NAMES:
        output['side_breakdown'][key]={}
        for period in ('selection','following-year','full'):
            trades=read(RUNTIME/f'{key}-{period}.json')['trades']
            output['side_breakdown'][key][period]={side:summarize([t for t in trades if t['side']==side],include_streak=True) for side in ('long','short')}
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
                cmd.update(strategy='trend_cloud_context_v3',parameters={**v['parameters'],'record_indicators':True})
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
