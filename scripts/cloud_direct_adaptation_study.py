"""Frozen mechanism experiment; formulas use prices only, never P&L selection."""
import argparse
from bisect import bisect_left,bisect_right
from concurrent.futures import ProcessPoolExecutor,as_completed
from itertools import product
from math import isclose
from pathlib import Path
import json
import numpy as np
from app.domain.local_backtest import simulate as original
from app.domain.cloud_adaptive_research_v1 import simulate
from app.domain.backtest_history import validate_observed_bars
from app.domain.cloud_trade_attribution import summary,compound,calendar_returns,periods,stress
from app.services.local_backtest_strategies import load_strategy,validate_parameters,digest
from scripts.btc_cloud_parameter_study import BASE,freeze
from scripts.cloud_walkforward_study import read_zip,write_zip
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT,read,save
from scripts.trend_cloud_study import stamp

DOCS=ROOT/'docs/verification/cloud-direct-adaptation-20260912'
RUNTIME=ROOT/'.heimdall_runtime/cloud-direct-adaptation-20260912'
SOURCE=ROOT/'strategies/trend_cloud_direct_v7.py'
ASSETS=('paxg','zec','eth','btc');TFS={'15m':900000,'1h':3600000}
START='2020-10-01T00:00:00Z';SPLIT='2024-09-10T00:00:00Z';END='2026-09-10T00:00:00Z';WARMUP=650


def variants():
    _,spec=load_strategy(SOURCE);out={}
    for c,r,t in product((False,True),repeat=3):
        k=f'c{int(c)}r{int(r)}t{int(t)}'
        label='原版' if not any((c,r,t)) else '＋'.join(n for enabled,n in [(c,'自动均线'),(r,'波动止损与启动'),(t,'波动跟踪保护')] if enabled)
        out[k]=dict(label=label,parameters=validate_parameters(spec,{**BASE,'adaptive_center':c,'scaled_risk':r,'atr_trailing':t}))
    for k,label,changes in [
        ('base_gate','原版＋入场方向效率过滤',dict(efficiency_gate=True)),
        ('adaptive_gate','三项自适应＋入场方向效率过滤',dict(adaptive_center=True,scaled_risk=True,atr_trailing=True,efficiency_gate=True)),
        ('slow89','只把固定EMA55改为EMA89',dict(center_length=89)),
        ('wide12','只把突破门槛0.4改为1.2倍',dict(trigger_mult=1.2))]:
        out[k]=dict(label=label,parameters=validate_parameters(spec,{**BASE,**changes}))
    return out


def prepare():
    if (DOCS/'plan.json').exists():return
    sources=[Path(__file__),SOURCE,ROOT/'app/domain/cloud_adaptive_types_v1.py',ROOT/'app/domain/cloud_adaptive_research_v1.py',
        ROOT/'app/domain/local_backtest.py',ROOT/'strategies/trend_cloud_parameters_v4.py',ROOT/'app/domain/cloud_trade_attribution.py',ROOT/'test/test_cloud_direct_adaptation.py']
    data=read(ROOT/'docs/verification/cloud-short-window-20260912/data.json')
    plan=dict(assets=ASSETS,timeframes=TFS,start=START,end=END,split=SPLIT,variants=variants(),
        data={a:{tf:data[a][tf] for tf in TFS} for a in ASSETS},warmup=WARMUP,
        sources={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in sources},
        purpose='Test price-derived rules, not a return-ranked parameter selector. Primary15m diagnoses original failures;1h fixed independent scale comparison. Never switch timeframe or promote its ex-post winner.',
        center='HL2 EMA; ER31=abs(close-close31)/sum(abs(each31close change)). alpha=2/90+ER*(2/22-2/90). EffectiveEMA21..89. This is linear adaptive EMA, NOT squared-factor standard KAMA. Endpoints from already discussed ranges, not claimed optimal.',
        entry='Preserve width EMA(high-low)31, crossing center +/-0.4W, chase limit2W, next-open fill. Only center changes in center arm. Fixed89 and trigger1.2 paired controls test oversensitivity. No confirmed-pivot/future inputs.',
        risk='Risk arm uses2ATR14 initial absolute distance and4ATR14 activation distance, both frozen at signal close and anchored to actual next fill. No ATR expansion widens initial stop. Original1% and2% otherwise. These multiples are fixed hypotheses, not optimal estimates.',
        trail='After activation, ratchet to favourable peak minus2currentATR14 (short mirrored), never past loss-side of entry and never loosen. Current closed-bar high/low andATR update next bar only. Original50%giveback otherwise. Gap exit at actual open.',
        gate='Gate controls require ER31>=0.2 on signal close for entry only. Raw opposite crossing still closes even if gate/chase blocks reverse entry. Original+gate and fulladaptive+gate are both run, never chosen by P&L.0.2 is a fixed hypothesis, not proven predictive.',
        periods='Continuous2020-10-01 to2026-09-10 with650warmup bars. Report early and later two-year equity growth; same frozen formulas all years. No ranking uses earlier or later profits. Historical data already studied, not untouched holdout.',
        diagnostic='Exit labels describe loss mechanisms, not sufficient causes. Paired intervention, annuals, sides, frequency, rapid reversal <=4bars, peak before exit, pre-entryER groups and baseline post-entry4/16bar continuation quantify the oversensitivity hypothesis. Forward diagnostics descriptive only and never used for trading. Retain all trades and raw crossing audits.',
        acceptance='Report whether fulladaptive beats original and is positive on full and later periods separately per asset/timeframe; year count, low win rate and profit concentration disclosed. Do not expand formulas after results to force PAXG/ZEC profitable.',
        costs=dict(initial_cash=10000,position_pct=100,leverage=1,fees=0,slippage=0),total_simulations=96)
    freeze(DOCS/'plan.json',plan);snapshot('070-frozen-direct-adaptation',[*sources,DOCS/'plan.json'])
    print('FROZEN96 runs:4 assets x2 fixed timeframes x12 mechanistic variants',flush=True)


def check():
    p=read(DOCS/'plan.json')
    for f,h in p['sources'].items():assert digest((ROOT/f).read_bytes())==h,f
    return p


def describe(result,rows,audit,step):
    trades=result['trades'];eq=result['equity'];m=summary(trades)
    m.update(return_pct=result['report']['return_pct'],max_drawdown_pct=result['report']['max_drawdown_pct'])
    assert isclose(m['compound_return_pct'],m['return_pct'],abs_tol=1e-6,rel_tol=1e-9)
    ts=[e['timestamp'] for e in eq];i=bisect_right(ts,stamp(SPLIT))-1
    assert ts[i]==stamp(SPLIT)
    m.update(early_return_pct=100*(eq[i]['equity']/10000-1),later_return_pct=100*(eq[-1]['equity']/eq[i]['equity']-1))
    assert isclose((1+m['early_return_pct']/100)*(1+m['later_return_pct']/100),1+m['return_pct']/100,rel_tol=1e-9)
    exits={r:summary([t for t in trades if t['exit_reason']==r]) for r in sorted({t['exit_reason'] for t in trades})}
    losses=[t for t in trades if t['return_pct']<0]
    rapid=[t for t in losses if t['exit_reason'] in ('signal','reversal') and t['duration_minutes']<=4*step/60000]
    m.update(rapid_reversal_losses=len(rapid),protected_trades=sum(bool(t.get('protection_active')) for t in trades),
        losing_mean_peak_pct=float(np.mean([t.get('profit_peak_pct',0.) for t in losses])) if losses else None,
        blocked_efficiency=sum(x['near'] and not x['efficient'] for x in audit),raw_crossings=len(audit))
    years=calendar_returns(eq,rows,periods(stamp(START),stamp(END),'year'))
    months=calendar_returns(eq,rows,periods(stamp(START),stamp(END),'month'))
    m['positive_full_years']=sum(y['return_pct']>0 for y in years if '2021'<=y['label']<='2025')
    at={x['timestamp']:x for x in audit};times=[r[0] for r in rows];tagged=[]
    for t in trades:
        j=bisect_left(times,t['entry_time'])-1;s=at[times[j]]
        tagged.append(dict(t,signal_er=s['er'],signal_atr_pct=s['atr_pct'],signal_equivalent_ema=s['equivalent_ema']))
    groups={k:summary([t for t in tagged if (t['signal_er']>=.2)==ok]) for k,ok in [('er_below_02',False),('er_atleast_02',True)]}
    stride=max(1,len(eq)//600);curve=[{k:e[k] for k in ('timestamp','equity')} for e in eq[::stride]]
    if curve[-1]['timestamp']!=eq[-1]['timestamp']:curve.append({k:eq[-1][k] for k in ('timestamp','equity')})
    return dict(metrics=m,exits=exits,sides={s:summary([t for t in trades if t['side']==s]) for s in ('long','short')},
        years=years,months=months,entry_groups=groups,concentration=stress(trades,months),curve=curve)


def forward_diagnostic(trades,audit,rows,step):
    times=[r[0] for r in rows];at={x['timestamp']:x for x in audit};out=[]
    for t in trades:
        i=bisect_left(times,t['entry_time']);s=at[times[i-1]];d=t['direction'];entry=t['entry_price']
        x=dict(entry_time=t['entry_time'],side=t['side'],er=s['er'],atr_pct=s['atr_pct'],trade_return=t['return_pct'])
        for n in (4,16):
            j=i+n-1
            if j>=len(rows) or times[j]-times[i]!=(n-1)*step:continue
            close=rows[j][4]
            x[f'forward_{n}_atr']=d*(close-entry)/s['atr']
        out.append(x)
    groups={}
    for k,pred in [('all',lambda t:True),('er_below_02',lambda t:t['er']<.2),('er_atleast_02',lambda t:t['er']>=.2)]:
        group=[t for t in out if pred(t)];g={}
        for n in (4,16):
            vals=[t[f'forward_{n}_atr'] for t in group if f'forward_{n}_atr' in t]
            g[str(n)]=dict(samples=len(vals),mean_directional_atr=float(np.mean(vals)) if vals else None,
                directional_positive_pct=100*sum(v>0 for v in vals)/len(vals) if vals else None)
        groups[k]=g
    return dict(groups=groups,records=out)


def worker(task):
    a,tf=task;p=check();step=TFS[tf];rec=p['data'][a][tf];path=ROOT/rec['path']
    raw=path.read_bytes();assert digest(raw)==rec['data_hash'];rows=json.loads(raw);times=[r[0] for r in rows]
    i,j=bisect_left(times,stamp(START)),bisect_left(times,stamp(END));rows=rows[i-WARMUP:j]
    bars,gaps=validate_observed_bars(rows,stamp(START),stamp(END),step,WARMUP,stamp(END))
    result={};provenance=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),data_hash=rec['data_hash'])
    for k,v in p['variants'].items():
        dest=RUNTIME/'traces'/a/f'{tf}-{k}.json.gz';report=DOCS/'reports'/a/f'{tf}-{k}.json'
        if dest.exists() and report.exists():
            saved=read(report);assert saved['provenance']==provenance and digest(dest.read_bytes())==saved['trace_hash'];result[k]=saved;continue
        module,_=load_strategy(SOURCE)
        trace=simulate(bars,module,v['parameters'],warmup=WARMUP,step_ms=step)
        audit=module._calculation.audit
        desc=describe(trace,rows,audit,step)
        if k=='c0r0t0':
            old,_=load_strategy(SOURCE.parent/'trend_cloud_parameters_v4.py')
            control=original(bars,old,BASE,warmup=WARMUP,step_ms=step)
            assert trace==control,(a,tf,'original mismatch');desc['original_engine_exact']=True
            diag=forward_diagnostic(trace['trades'],audit,rows,step)
            freeze(DOCS/'diagnostics'/f'{a}-{tf}.json',diag['groups'])
            write_zip(RUNTIME/'diagnostics'/f'{a}-{tf}.json.gz',diag)
            del control
        trace.update(provenance=provenance,parameters=v['parameters'],crossings=audit)
        write_zip(dest,trace)
        desc.update(provenance=provenance,trace_path=dest.relative_to(ROOT).as_posix(),trace_hash=digest(dest.read_bytes()),
            gaps=gaps,missing_bars=sum(g['missing_bars'] for g in gaps),asset=a,timeframe=tf,variant=k)
        freeze(report,desc);result[k]=desc
        print('DONE',a,tf,k,'full',round(desc['metrics']['return_pct'],2),'later',round(desc['metrics']['later_return_pct'],2),flush=True)
        del trace,audit,module
    return a,tf,result


def study(workers):
    p=check();results={a:{} for a in ASSETS}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs=[pool.submit(worker,(a,tf)) for a in ASSETS for tf in TFS]
        for f in as_completed(jobs):
            a,tf,r=f.result();results[a][tf]=r
    verification=dict(status='passed',simulations=96,original_exact_controls=8,
        tests='test/test_cloud_direct_adaptation.py',no_return_selection=True)
    freeze(DOCS/'results.json',dict(status='completed',plan=p,results=results,verification=verification))
    print('COMPLETE96 fixed-formula tests;8 original controls exact',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run']);ap.add_argument('--workers',type=int,default=2);args=ap.parse_args()
    prepare() if args.action=='prepare' else study(args.workers)
