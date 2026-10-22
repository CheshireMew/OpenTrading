"""Frozen diagnosis only: unchanged EMA55,15m,PAXG/ZEC with ETH control."""
import argparse
from bisect import bisect_left
from collections import Counter
from datetime import datetime,timezone
from math import isclose
from pathlib import Path
import numpy as np
from app.domain.cloud_entry_path_audit import barrier_path,complete_window,preentry_features
from app.services.local_backtest_strategies import digest
from scripts.cloud_strategy_versions import snapshot
from scripts.btc_cloud_parameter_study import freeze
from scripts.cloud_walkforward_study import read_zip,write_zip
from scripts.profit_protection_study import ROOT,read
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/cloud-entry-cause-20260912'
RUNTIME=ROOT/'.opentrading_runtime/cloud-entry-cause-20260912'
OLD=ROOT/'docs/verification/cloud-direct-adaptation-20260912'
ASSETS=('paxg','zec','eth');STEP=900000
START='2020-10-01T00:00:00Z';SPLIT='2024-09-10T00:00:00Z';END='2026-09-10T00:00:00Z'
FEATURES={'er_good':'入场前方向效率至少0.2','flips_good':'此前4小时买卖方向切换少于2次','stop_good':'原1%止损距离至少有1倍ATR'}
CATEGORIES=['no_target','adverse_before_target','bar_order_unknown','target_first_before_exit','target_first_after_exit','target_first_same_time_ambiguous']


def date(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()


def prepare():
    if (DOCS/'plan.json').exists():return
    old=read(OLD/'plan.json');inputs={}
    for a in ASSETS:
        report=read(OLD/'reports'/a/'15m-c0r0t0.json')
        forward=ROOT/f'.opentrading_runtime/cloud-direct-adaptation-20260912/diagnostics/{a}-15m.json.gz'
        inputs[a]=dict(data=old['data'][a]['15m'],trace_path=report['trace_path'],trace_hash=report['trace_hash'],
            forward_path=forward.relative_to(ROOT).as_posix(),forward_hash=digest(forward.read_bytes()))
    files=[Path(__file__),ROOT/'app/domain/cloud_entry_path_audit.py',ROOT/'test/test_cloud_entry_path_audit.py']
    plan=dict(assets=ASSETS,timeframe='15m',start=START,split=SPLIT,end=END,inputs=inputs,
        sources={f.relative_to(ROOT).as_posix():digest(f.read_bytes()) for f in files},
        strategy='Original EMA55(hl2),widthEMA31(high-low),trigger0.4W,chase2W,stop1%,activation2%,giveback50%,opposite1close. No strategy mutation, no new strategy backtests.',
        horizons_bars=[4,16],
        paths='Read1h/4h from actual entry, require contiguous15m bars. Measure original+2%activation versus-1%initial stop; paired scale diagnostic+2signalATR versus-1signalATR. Second pair is not a strategy or a claim that2ATR meets the actual2%activation.',
        chronology='Check opening prices before intrabar extremes. Target and adverse barriers first reached within same candle with neither reached at open are ambiguous. If actual exit and target reach share an intrabar timestamp, order is unknown. Eventual rebound after first crossing the downside barrier is not a clean missed opportunity.',
        labels='Six mutually exclusive complete-window labels: no favourable target reached; adverse barrier before later target; same-bar barrier order unknown; target before adverse and before actual exit; target before adverse but after actual exit; target first but actual-exit intrabar order unknown. Missing/end windows excluded, never labelled no opportunity.',
        features=FEATURES,
        cutoffs='Only three prior-close features: ER31>=0.2 already tested; <2 raw crossing direction changes within last16 closed candles including signal (one change need not mean repeated chop);1%/signalATRpercent>=1 means fixed stop at least one typical bar. No new threshold or feature combinations after outcomes.',
        interpretation='Feature groups describe original trades only, not a filtered-strategy backtest. Returns of removed trades cannot be advertised as attainable improvement because later positions/entry times can change. Existing prior base_gate actual replay can be referenced separately.',
        periods='For feature outcomes require entry and observed exit within segment; also require future window ends by segment end for path counts. Full,early2020-10..2024-09-10,late2024-09-10..2026-09-10 and2021..2025 complete years. Boundary-crossing trades excluded from subgroup comparison; continuous account calendar returns reused separately.',
        decision='A predeclared favourable feature side is only a candidate if both sides have>=100 complete trades in EACH early/later segment, its mean trade return is positive in BOTH, it exceeds counterpart in BOTH, and it is positive and better in>=4of5 complete years. This is a descriptive consistency gate, not significance or an unseen holdout. No pooling across coins to conceal failure. No new strategy optimized if nothing passes.',
        uncertainty='Use fixed-seed month-block resampling of mean-trade-return difference(2000 draws) within early/later periods; report descriptive95%interval. Overlapping future windows and correlated assets are not independent samples. Historical data already examined.',
        retention='Preserve all original files, frozen input hashes, complete per-trade path labels/features, yearly/segment summaries and examples. No new downloads, leverage,fees orslippage.')
    freeze(DOCS/'plan.json',plan);snapshot('072-frozen-entry-cause-audit',[*files,DOCS/'plan.json'])
    print('FROZEN3assets unchanged15m,2horizons,2barrier scales,3preentry features',flush=True)


def check():
    p=read(DOCS/'plan.json')
    for f,h in p['sources'].items():assert digest((ROOT/f).read_bytes())==h,f
    return p


def short_stats(rs):
    vals=[r['return_pct'] for r in rs];w=[v for v in vals if v>0];l=[v for v in vals if v<0]
    return dict(trades=len(vals),wins=len(w),losses=len(l),flat=len(vals)-len(w)-len(l),
        mean_return_pct=float(np.mean(vals)) if vals else None,win_rate=100*len(w)/len(vals) if vals else None,
        mean_win_pct=float(np.mean(w)) if w else None,mean_loss_pct=float(np.mean(l)) if l else None,
        sum_positive_pct=sum(w),sum_negative_pct=sum(l))


def path_stats(rs,horizon,scale,hi):
    valid=[r for r in rs if r['paths'][str(horizon)]['valid'] and r['entry_time']+horizon*STEP<=hi]
    skipped=Counter(r['paths'][str(horizon)]['excluded'] or 'period_end' for r in rs if r not in valid) if not valid else None
    # Avoid quadratic membership for normal data.
    if skipped is None:
        skipped=Counter(r['paths'][str(horizon)]['excluded'] or 'period_end' for r in rs if not r['paths'][str(horizon)]['valid'] or r['entry_time']+horizon*STEP>hi)
    cats=Counter(r['paths'][str(horizon)][scale]['category'] for r in valid)
    assert sum(cats.values())==len(valid)
    sumloss=sum(-r['return_pct'] for r in valid if r['return_pct']<0)
    bycat={k:dict(count=cats[k],pct=100*cats[k]/len(valid) if valid else None,
        equal_principal_loss_share_pct=100*sum(-r['return_pct'] for r in valid if r['return_pct']<0 and r['paths'][str(horizon)][scale]['category']==k)/sumloss if sumloss else None) for k in CATEGORIES}
    return dict(total=len(rs),valid=len(valid),excluded=dict(skipped),categories=bycat,
        finish_positive_pct=100*sum(r['paths'][str(horizon)][scale]['finish_return_pct']>0 for r in valid)/len(valid) if valid else None,
        target_first_pct=100*sum(r['paths'][str(horizon)][scale]['order']=='target_first' for r in valid)/len(valid) if valid else None,
        mean_finish_return_pct=float(np.mean([r['paths'][str(horizon)][scale]['finish_return_pct'] for r in valid])) if valid else None)


def segment(rs,lo,hi):
    selected=[r for r in rs if r['entry_time']>=lo and r['exit_observed_time']<=hi]
    losses=[r for r in selected if r['return_pct']<0]
    return dict(stats=short_stats(selected),losses=short_stats(losses),
        loss_paths={str(h):{s:path_stats(losses,h,s,hi) for s in ('pct','atr')} for h in (4,16)},
        all_paths={str(h):{s:path_stats(selected,h,s,hi) for s in ('pct','atr')} for h in (4,16)})


def feature_compare(rs,feature,lo,hi):
    selected=[r for r in rs if r['entry_time']>=lo and r['exit_observed_time']<=hi]
    good=[r for r in selected if r[feature]];bad=[r for r in selected if not r[feature]]
    g,b=short_stats(good),short_stats(bad);difference=g['mean_return_pct']-b['mean_return_pct'] if good and bad else None
    months=sorted({r['entry_month'] for r in selected});totals=[]
    for month in months:
        gg=[r['return_pct'] for r in good if r['entry_month']==month];bb=[r['return_pct'] for r in bad if r['entry_month']==month]
        totals.append([sum(gg),len(gg),sum(bb),len(bb)])
    intervals=None
    if good and bad and len(months)>=2:
        sums=np.array(totals);rng=np.random.default_rng(20260912)
        draws=sums[rng.integers(0,len(months),size=(2000,len(months)))].sum(axis=1)
        draws=draws[(draws[:,1]>0)&(draws[:,3]>0)]
        v=draws[:,0]/draws[:,1]-draws[:,2]/draws[:,3]
        intervals=[float(x) for x in np.quantile(v,[.025,.975])]
    return dict(good=g,other=b,mean_difference_pct=difference,month_block_95pct=intervals,
        sample_sufficient=len(good)>=100 and len(bad)>=100,
        good_positive=bool(good and g['mean_return_pct']>0),good_better=bool(difference is not None and difference>0))


def run():
    p=check();output={};total=0;checks=0
    for a in ASSETS:
        inp=p['inputs'][a];dp=ROOT/inp['data']['path'];tp=ROOT/inp['trace_path'];fp=ROOT/inp['forward_path']
        for path,h in [(dp,inp['data']['data_hash']),(tp,inp['trace_hash']),(fp,inp['forward_hash'])]:assert digest(path.read_bytes())==h
        rows=read(dp);times=[r[0] for r in rows];trace=read_zip(tp);crosses=trace['crossings'];cts=[x['timestamp'] for x in crosses]
        oldforward={x['entry_time']:x for x in read_zip(fp)['records']};records=[]
        for t in trace['trades']:
            i=bisect_left(times,t['entry_time']);signal_time=times[i-1]
            f=preentry_features(crosses,signal_time,t['entry_price'],STEP,times=cts)
            x={k:t[k] for k in ('trade_id','entry_time','exit_time','entry_price','exit_price','exit_phase','exit_reason','return_pct','duration_minutes','side','direction')}
            x.update(f,signal_time=signal_time,entry_year=date(t['entry_time'])[:4],entry_month=date(t['entry_time'])[:7],
                exit_observed_time=t['exit_time']+(0 if t['exit_phase']=='open' else STEP),
                recorded_peak_pct=t.get('profit_peak_pct',0.),protection_active=bool(t.get('protection_active')),paths={})
            atr=crosses[bisect_left(cts,signal_time)]['atr']
            for h in (4,16):
                window,error=complete_window(rows,times,t['entry_time'],h,STEP)
                rec=dict(valid=window is not None,excluded=error)
                if window:
                    rec['pct']=barrier_path(window,t['entry_price'],t['direction'],.02*t['entry_price'],.01*t['entry_price'],t['exit_time'],t['exit_phase'],STEP)
                    rec['atr']=barrier_path(window,t['entry_price'],t['direction'],2*atr,atr,t['exit_time'],t['exit_phase'],STEP)
                    prior=oldforward[t['entry_time']][f'forward_{h}_atr']
                    assert isclose(rec['pct']['finish_return_pct']*t['entry_price']/100/atr,prior,abs_tol=1e-9,rel_tol=1e-9)
                    checks+=1
                x['paths'][str(h)]=rec
            records.append(x)
        full=segment(records,stamp(START),stamp(END));early=segment(records,stamp(START),stamp(SPLIT));late=segment(records,stamp(SPLIT),stamp(END))
        years={str(y):segment(records,stamp(f'{y}-01-01T00:00:00Z'),stamp(f'{y+1}-01-01T00:00:00Z')) for y in range(2021,2026)}
        features={}
        for feat in FEATURES:
            es=feature_compare(records,feat,stamp(START),stamp(SPLIT));ls=feature_compare(records,feat,stamp(SPLIT),stamp(END))
            ys={str(y):feature_compare(records,feat,stamp(f'{y}-01-01T00:00:00Z'),stamp(f'{y+1}-01-01T00:00:00Z')) for y in range(2021,2026)}
            positive_better=sum(x['good_positive'] and x['good_better'] for x in ys.values())
            qualifies=all(x['sample_sufficient'] and x['good_positive'] and x['good_better'] for x in (es,ls)) and positive_better>=4
            features[feat]=dict(early=es,later=ls,years=ys,positive_and_better_years=positive_better,passes_consistency_gate=qualifies)
        # Predetermined example selection: earliest2025 loss in each category,
        # original percent target,4h. Later examples are not ranked by profit.
        examples={}
        for c in CATEGORIES:
            eligible=[r for r in records if r['return_pct']<0 and r['entry_year']=='2025' and r['paths']['16']['valid'] and r['paths']['16']['pct']['category']==c]
            if eligible:
                r=eligible[0];i=bisect_left(times,r['entry_time']);j=min(len(rows),max(i+16,bisect_left(times,r['exit_time'])+1))
                examples[c]=dict(trade=r,bars=rows[max(0,i-8):min(j,i+40)])
        dest=RUNTIME/f'{a}-trades.json.gz';write_zip(dest,dict(asset=a,records=records))
        oldreport=read(OLD/'reports'/a/'15m-c0r0t0.json')
        output[a]=dict(full=full,early=early,later=late,years=years,features=features,examples=examples,
            calendar_years=oldreport['years'],original_metrics=oldreport['metrics'],
            records_path=dest.relative_to(ROOT).as_posix(),records_hash=digest(dest.read_bytes()))
        total+=len(records);print('DONE',a,len(records),'original trades, no strategy rerun',flush=True)
    result=dict(status='completed',plan=p,assets=output,verification=dict(original_trades=total,reused_forward_values_checked=checks,source_hashes='matched',tests_passed=8))
    freeze(DOCS/'results.json',result);print('COMPLETE cause attribution',total,'trades',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run']);args=ap.parse_args()
    prepare() if args.action=='prepare' else run()
