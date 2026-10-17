"""Bounded study with win/loss count as an explicit manual-trading gate."""
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
from scripts.cloud_robustness_study import ROOT,stitched
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import metrics,read,save
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/eth-cloud-manual-20260910'
RUNTIME=ROOT/'.heimdall_runtime/cloud-manual-20260910'
SOURCE=ROOT/'strategies/trend_cloud_manual_v1.py'
BASELINE=ROOT/'.heimdall_runtime/local_backtests/f6bdf2e5831c468381a1a7c224ec1afa'


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Do not overwrite the frozen manual-trading study')
    variants={}
    def add(key,name,group,**changes):
        p=dict(entry_mode='cross',confirmation_bars=2,retest_bars=8,efficiency_threshold=.2,
               activation_pct=2,giveback_pct=50,record_indicators=False)
        p.update(changes)
        variants[key]=dict(name=name,group=group,parameters=p)
    add('baseline','原过滤震荡 20% 版','reference')
    add('confirm2','突破后连续两根收在通道外','entry',entry_mode='confirm',confirmation_bars=2)
    add('confirm3','突破后连续三根收在通道外','entry',entry_mode='confirm',confirmation_bars=3)
    add('retest4','突破后等回踩收回，最多等一小时','entry',entry_mode='retest',retest_bars=4)
    add('retest8','突破后等回踩收回，最多等两小时','entry',entry_mode='retest',retest_bars=8)
    add('efficiency40','只做过去八小时更顺畅的走势（40%）','entry',efficiency_threshold=.4)
    add('protect05','浮盈 0.5% 就保护，允许回吐 40%','exit',activation_pct=.5,giveback_pct=40)
    add('protect10','浮盈 1% 就保护，允许回吐 40%','exit',activation_pct=1,giveback_pct=40)
    add('giveback30','仍盈利 2% 启动，但只许回吐 30%','exit',giveback_pct=30)
    add('runner3','盈利 3% 才保护，允许回吐 60%','exit',activation_pct=3,giveback_pct=60)
    add('confirm2protect05','两根确认＋浮盈 0.5% 保护','combined',entry_mode='confirm',activation_pct=.5,giveback_pct=40)
    add('retest8protect10','回踩确认＋浮盈 1% 保护','combined',entry_mode='retest',activation_pct=1,giveback_pct=40)
    boundaries=['2025-09-10','2025-12-10','2026-03-10','2026-06-10','2026-09-10']
    periods={'selection':['2024-09-10T00:00:00Z','2025-09-10T00:00:00Z']}
    periods.update({f'q{i+1}':[a+'T00:00:00Z',b+'T00:00:00Z'] for i,(a,b) in enumerate(zip(boundaries,boundaries[1:]))})
    periods['full']=['2024-09-10T00:00:00Z','2026-09-10T00:00:00Z']
    plan=dict(created_at=datetime.now(timezone.utc).isoformat(),symbol='ETH/USDT',timeframe='15m',
              start=periods['full'][0],end=periods['full'][1],initial_cash=10000,position_pct=100,warmup=650,
              data_hash='ca0edb3d7493df0da568b8cad6355a894de8c44cde82cd42c207704e3b0e90f7',variants=variants,periods=periods,
              objective='Manual execution: winning trades must outnumber losing trades. Also inspect expectancy, streaks, frequency and whether winners earn more. Do not force a successful result.',
              selection='Using only the first year, require wins > losses, positive return, >=50 trades. Rank return/max drawdown, then return, then ID. Lock before later-period evaluation. If none qualify, no recommended candidate; do not replace with a retrospective winner.',
              acceptance={'full_wins_greater_than_losses':True,'following_year_wins_greater_than_losses':True,
                          'following_year_positive_return':True,'quarters_positive_min':3,'quarters_wins_exceed_losses_min':3,
                          'following_year_min_trades':50,'following_year_max_drawdown_pct':25},
              execution=['Same no-cost engine v4, no leverage, 100% current account equity per entry. Close signals, next open execution.',
                         'Profit protection OR raw opposite crossing independently exits. Entry confirmations never delay opposite-signal exit. No added fixed target, initial stop, scaling out, averaging down or wider loss limit.',
                         'Confirmation requires 2/3 consecutive closes beyond the same dynamic band after a crossing. Return inside cancels the pending entry. Evaluate chase and efficiency at the actual entry decision.',
                         'Retest waits at least one bar after crossing, at most 4/8 bars. Long: low touches dynamic upper band, close back above; short symmetric. Close through the center or opposite crossing invalidates previous wait. It is a close-confirmed signal; no intrabar assumption about fill.',
                         'Same-side signals do not add holdings. No calendar trading-hour filter. Exposure around the clock is reported as a manual-execution burden.',
                         'Protection uses favorable high/low known by each close; revised line starts next bar. Gaps execute at actual open. It does not guarantee exact retained profit.'],
              diagnostics=['Classify original losses by pre-entry direction and peak favorable return recorded by engine before exit.',
                           'Report average winning/losing returns, average hold time, median and 90th percentile trades per UTC day, consecutive losses, side and exit contributions.',
                           'Do not label lower gross-return strategies better merely because win rate rises; compare return and average loss too.'],
              stop_rule='Only these 12 predefined candidates. One newly authorized study after the user explicitly prioritised manual-trading win/loss count. If no first-year candidate passes the later acceptance gates, conclude this family does not yet meet the requirement; no further grid expansion.',
              caveat='The entire two-year history has already been seen. This new goal changes the selection criterion, but cannot turn reused history into independent proof. Confirmation/filter hypotheses may fail; keep them. Historical >50% wins cannot guarantee future win rate.')
    save(DOCS/'plan.json',plan)
    RUNTIME.mkdir(parents=True,exist_ok=True)
    snapshot('011-frozen-manual-study',[SOURCE,ROOT/'scripts/cloud_manual_study.py',DOCS/'plan.json',ROOT/'test/test_cloud_manual.py'])
    print('Frozen 12 variants; 72 simulations; win/loss gate before ranking',flush=True)


def select(training):
    eligible=[k for k,r in training.items() if r['wins']>r['losses'] and r['return_pct']>0 and r['total_trades']>=50]
    return sorted(eligible,key=lambda k:(-(training[k]['return_to_drawdown'] or 0),-training[k]['return_pct'],k))


def entry_frequency(trades,start,end):
    n=(stamp(end)-stamp(start))//86400000
    counts=[0]*n
    for t in trades:
        day=(t['entry_time']-stamp(start))//86400000
        counts[day]+=1
    ordered=sorted(counts)
    mid=n//2
    return dict(average_trades_per_day=len(trades)/n,days_with_trades=sum(c>0 for c in counts),
                median_trades_per_day=ordered[mid] if n%2 else (ordered[mid-1]+ordered[mid])/2,
                p90_trades_per_day=ordered[min(n-1,int(.9*n))],max_trades_per_day=max(counts),
                note='Entries per UTC day, including days without trades. Continuous 24-hour simulation; human availability is not modelled.')


def study():
    plan=read(DOCS/'plan.json')
    files=[SOURCE,ROOT/'scripts/cloud_manual_study.py',ROOT/'scripts/cloud_robustness_study.py',
           ROOT/'scripts/profit_protection_study.py',ROOT/'scripts/trend_cloud_study.py',ROOT/'app/domain/local_backtest.py',
           ROOT/'app/domain/backtest_diagnostics.py',ROOT/'app/services/local_backtest_strategies.py',DOCS/'plan.json']
    provenance=dict(files={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in files},environment=environment())
    raw=(BASELINE/'data.json').read_bytes()
    assert digest(raw)==plan['data_hash']
    provenance['data_hash']=digest(raw)
    bars=[Bar(int(r[0]),*map(float,r[1:])) for r in json.loads(raw)]
    times=[b.timestamp for b in bars]
    result_path=DOCS/'results.json'
    output=read(result_path) if result_path.exists() else dict(plan=plan,provenance=provenance,results={},status='running')
    assert output['provenance']==provenance,'Create a new version if any input changes'

    def calculate(key,period):
        path=RUNTIME/f'{key}-{period}.json'
        if period in output['results'].get(key,{}):
            r=read(path)
            assert r['provenance']==provenance
            return r
        start,end=plan['periods'][period]
        a,b=bisect_left(times,stamp(start)),bisect_left(times,stamp(end))
        assert a>=650 and b-a==(stamp(end)-stamp(start))//900000
        module,spec=load_strategy(SOURCE)
        p=validate_parameters(spec,plan['variants'][key]['parameters'])
        r=simulate(bars[a-650:b],module,p,warmup=650,step_ms=900000,initial_cash=10000,position_pct=100)
        if key=='baseline' and period=='full':
            old=read(BASELINE/'result.json')
            assert r['trades']==old['trades'] and r['equity']==old['equity']
            output['baseline_exact']=True
        m=metrics(r)
        m.update(entry_frequency(r['trades'],start,end))
        output['results'].setdefault(key,{})[period]=m
        trace={k:r[k] for k in ('report','trades','signals','equity')}
        trace.update(provenance=provenance,parameters=p,period=[start,end])
        save(path,trace)
        save(result_path,output)
        print(f'{period} {key}: return {m["return_pct"]:.2f}%, wins {m["wins"]}/{m["total_trades"]}, DD {m["max_drawdown_pct"]:.2f}%, loss streak {m["max_consecutive_losses"]}',flush=True)
        return trace

    for k in plan['variants']:
        calculate(k,'selection')
    ranking=select({k:v['selection'] for k,v in output['results'].items()})
    choice=dict(ranking=ranking,selected=ranking[0] if ranking else None,provenance=provenance)
    choice_path=DOCS/'selection.json'
    if choice_path.exists():
        assert read(choice_path)==choice
    else:
        save(choice_path,choice)
    output['selection']=choice
    save(result_path,output)
    print('LOCKED FIRST-YEAR CHOICE: '+str(choice['selected']),flush=True)
    output['following_year']={}
    for k in plan['variants']:
        parts=[(f'q{i}',calculate(k,f'q{i}')) for i in range(1,5)]
        joined=stitched(parts)
        report=dict(joined['report'])
        report.update(summarize(joined['trades'],include_streak=True))
        report.update(entry_frequency(joined['trades'],plan['periods']['q1'][0],plan['periods']['q4'][1]))
        report['average_duration_minutes']=sum(t['duration_minutes'] for t in joined['trades'])/len(joined['trades']) if joined['trades'] else None
        output['following_year'][k]=report
        save(RUNTIME/f'{k}-following-year.json',joined)
        calculate(k,'full')
    old=read(BASELINE/'result.json')
    groups={'same_8h_direction':[],'opposite_8h_direction':[],'loss_peak_under_05':[],'loss_peak_05_to_2':[],'loss_peak_atleast2':[]}
    for t in old['trades']:
        i=bisect_left(times,t['entry_time'])-1
        same=t['direction']*(bars[i].close-bars[i-32].close)>0
        groups['same_8h_direction' if same else 'opposite_8h_direction'].append(t)
        if t['profit']<0:
            peak=t.get('profit_peak_pct',0)
            groups['loss_peak_under_05' if peak<.5 else 'loss_peak_05_to_2' if peak<2 else 'loss_peak_atleast2'].append(t)
    output['baseline_loss_groups']={k:summarize(t) for k,t in groups.items()}
    c=plan['acceptance']
    passes={}
    for k in plan['variants']:
        q=[output['results'][k][f'q{i}'] for i in range(1,5)]
        f=output['results'][k]['full']; y=output['following_year'][k]
        checks=dict(full_win_count=f['wins']>f['losses'],following_year_win_count=y['wins']>y['losses'],
                    following_year_profit=y['return_pct']>0,quarter_profit=sum(r['return_pct']>0 for r in q)>=c['quarters_positive_min'],
                    quarter_win_count=sum(r['wins']>r['losses'] for r in q)>=c['quarters_wins_exceed_losses_min'],
                    sufficient_trades=y['total_trades']>=c['following_year_min_trades'],
                    drawdown=y['max_drawdown_pct']<=c['following_year_max_drawdown_pct'])
        passes[k]=dict(checks=checks,passed=all(checks.values()))
    output['acceptance']=passes
    output['accepted_selected_candidate']=choice['selected'] if choice['selected'] and passes[choice['selected']]['passed'] else None
    output['status']='completed'
    output['simulations']=sum(len(v) for v in output['results'].values())
    save(result_path,output)
    print(json.dumps({'selected':choice['selected'],'accepted':output['accepted_selected_candidate'],'passes':passes,'simulations':output['simulations']},ensure_ascii=False),flush=True)


def publish():
    r=read(DOCS/'results.json')
    assert r['status']=='completed'
    assert r['provenance']['files'][SOURCE.relative_to(ROOT).as_posix()]==digest(SOURCE.read_bytes())
    path=DOCS/'project-runs.json'
    receipt=read(path) if path.exists() else dict(provenance=r['provenance'],runs={})
    assert receipt['provenance']==r['provenance']
    database=build_database_runtime(settings)
    service=LocalBacktestService(database)
    try:
        for k,v in r['plan']['variants'].items():
            if k not in receipt['runs']:
                cmd={f:r['plan'][f] for f in ('symbol','timeframe','start','end','initial_cash','position_pct')}
                cmd.update(strategy='trend_cloud_manual_v1',parameters={**v['parameters'],'record_indicators':True})
                record=service.create(LocalBacktestCommand.model_validate(cmd))
                receipt['runs'][k]=dict(run_id=record['id'],verified=False)
                save(path,receipt)
            record=service.repository.get(receipt['runs'][k]['run_id'])
            if record['status']=='completed' and not receipt['runs'][k]['verified']:
                actual=read(service.directory(record['id'])/'result.json'); expected=read(RUNTIME/f'{k}-full.json')
                assert record['metadata']['data_hash']==r['provenance']['data_hash']
                assert actual['report']==expected['report'] and actual['trades']==expected['trades'] and actual['signals']==expected['signals']
                receipt['runs'][k]['verified']=True
                save(path,receipt)
            print(f'{k}: {record["status"]}, {record["id"]}, verified={receipt["runs"][k]["verified"]} {record.get("error") or ""}',flush=True)
    finally:
        database.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','publish'])
    args=parser.parse_args()
    {'prepare':prepare,'run':study,'publish':publish}[args.action]()
