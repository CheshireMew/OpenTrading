"""Inspect saved project trades. No backtest, parameter search, or future features."""
from collections import Counter
from datetime import datetime, timezone
from math import isclose, log1p
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from app.infra.research_files import file_hash, read_json
from app.domain.cloud_trade_attribution import summary, group, date

OUT = Path(__file__).parent
SOURCE = ROOT / 'docs/verification/bnb-intrabar-upgrade-20260913/loss-diagnosis/trades.json'
PLAN = read_json(OUT/'plan.json')
RUN = ROOT/'.heimdall_runtime/local_backtests'/PLAN['baseline_run']
SPLIT = int(datetime(2023,1,1,tzinfo=timezone.utc).timestamp()*1000)
CUTOFF = PLAN['candidate_cutoff_pct']


def save(name, value):
    with (OUT/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def describe(ts):
    w = [t for t in ts if t['return_pct']>0]
    l = [t for t in ts if t['return_pct']<0]
    return dict(**summary(ts),
        mean_log_return=sum(log1p(t['return_pct']/100) for t in ts)/len(ts) if ts else None,
        gross_win_equal100=sum(t['return_pct'] for t in w),
        gross_loss_equal100=-sum(t['return_pct'] for t in l),
        recorded_peak_at_least_2_pct=100*sum(t['profit_peak_pct']>=2 for t in ts)/len(ts) if ts else None,
        losing_exits=dict(sorted(Counter(t['exit_reason'] for t in l).items())))


def split_groups(ts):
    return {name:describe([t for t in ts if (t['width_pct_before_entry']<CUTOFF)==low])
        for name,low in [('low',True),('high',False)]}


def main():
    meta=read_json(RUN/'metadata.json')
    for name,key in [('result.json','result_hash'),('data.json','data_hash')]:
        assert file_hash(RUN/name)==meta[key], name
    raw=read_json(RUN/'result.json'); candles=read_json(RUN/'data.json')
    rows=read_json(SOURCE); original=raw['trades']
    assert len(rows)==len(original)==7903
    for a,b in zip(rows,original):
        assert all(a[k]==v for k,v in b.items())
    observations={r['timestamp']:r for r in raw['indicators']}
    prices={b[0]:b[4] for b in candles}
    for t in rows:
        stamp=t['entry_order_signal_time']
        assert stamp+900000<=t['entry_time']
        width=100*observations[stamp]['values']['宽度基准']/prices[stamp]
        assert isclose(width,t['width_pct_before_entry'],abs_tol=1e-12)
        t['entry_year']=datetime.fromtimestamp(t['entry_time']/1000,timezone.utc).year
        t['entry_month']=date(t['entry_time'])[:7]
        t['volatility_group']='low' if width<CUTOFF else 'high'
    assert isclose(summary(rows)['compound_return_pct'],raw['report']['return_pct'],rel_tol=1e-9)
    del raw, candles, observations, prices

    # No open trade's later outcome is allowed to decide the early-period gate.
    dev=[t for t in rows if t['exit_time']<SPLIT]
    later=[t for t in rows if t['entry_time']>=SPLIT]
    crossing=[t for t in rows if t['entry_time']<SPLIT<=t['exit_time']]
    years=[]
    for y in sorted({t['entry_year'] for t in rows}):
        ys=[t for t in rows if t['entry_year']==y]
        if y<2023:ys=[t for t in ys if t['exit_time']<SPLIT]
        years.append(dict(year=y,**split_groups(ys)))
    early=[y for y in years if y['year'] in PLAN['development_full_years']]
    d=split_groups(dev)
    comparison={
        'enough_samples':all(y[k]['trades']>=100 for y in early for k in ['low','high']),
        'years_low_worse':[y['year'] for y in early if y['low']['mean_log_return']<y['high']['mean_log_return']],
        'pooled_low_negative':d['low']['sum_trade_return_pct']<0 and d['low']['log_growth']<0,
        'pooled_high_positive':d['high']['sum_trade_return_pct']>0 and d['high']['log_growth']>0}
    supported=(comparison['enough_samples'] and len(comparison['years_low_worse'])>=3
        and comparison['pooled_low_negative'] and comparison['pooled_high_positive'])
    winners=sorted([t for t in rows if t['return_pct']>0],key=lambda t:t['return_pct'],reverse=True)
    top=winners[:20]
    top_low=[t for t in top if t['volatility_group']=='low']
    months=[]
    for m in sorted({t['entry_month'] for t in rows}):
        months.append(dict(month=m,**split_groups([t for t in rows if t['entry_month']==m])))
    drawdown=[t for t in rows if 1659118500000<=t['exit_time']<1705770000000]
    result=dict(created_at=datetime.now(timezone.utc).isoformat(),baseline_run=RUN.name,
        plan_hash=file_hash(OUT/'plan.json'),analysis_hash=file_hash(Path(__file__)),
        source={k:file_hash(RUN/k) for k in ['result.json','data.json','strategy.py','engine.py']},
        annotated_source_hash=file_hash(SOURCE),feature_check='all 7903 widths match frozen pre-entry order observations',
        cutoff_pct=CUTOFF,development=d,later=split_groups(later),crossing_split_trades=crossing,
        years=years,all=split_groups(rows),three_buckets=group(rows,'width_bucket'),
        by_side={side:split_groups([t for t in rows if t['side']==side]) for side in ['long','short']},
        original_drawdown_trades=split_groups(drawdown),development_decision=comparison,
        run_filter_backtest=supported,
        top20_winners_blocked=dict(count=len(top_low),summary=describe(top_low),trades=top_low),
        notes=['每年按入场年份归组；开发期排除跨越2023分界后才知道结果的交易。',
               '0.4%为平滑单根高低差占价格比例，不是突破门槛0.8倍，也不是整个外侧通道宽度。',
               '等本金合计：每笔投入100时，单笔百分比数值等于金额；避免复利本金变化影响分组。',
               '复利分组仅是保留既有交易的事后归因，不能冒充过滤策略回测。',
               '全部历史此前已看过，后期仅作历史复核；没有未见数据或未来盈利保证。'])
    save('results.json',result);save('monthly.json',months)
    save('trade-classification.json',rows)
    keys=['trades','wins','losses','mean_return_pct','mean_log_return','sum_trade_return_pct',
          'gross_win_equal100','gross_loss_equal100','win_rate','recorded_peak_at_least_2_pct']
    compact=lambda v:{k:v[k] for k in keys}
    print(json.dumps(dict(supported=supported,decision=comparison,
        years=[dict(year=y['year'],low=compact(y['low']),high=compact(y['high'])) for y in years],
        development={k:compact(v) for k,v in d.items()},later={k:compact(v) for k,v in result['later'].items()},
        all={k:compact(v) for k,v in result['all'].items()},top20_blocked=len(top_low),
        original_drawdown={k:compact(v) for k,v in result['original_drawdown_trades'].items()}),ensure_ascii=False))


if __name__=='__main__':main()
