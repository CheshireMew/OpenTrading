"""Read-only profit-source audit of fixed, already-tested cloud strategies."""
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
from math import exp, log1p

from app.domain.backtest_diagnostics import summarize
from app.services.local_backtest_strategies import digest
from scripts.cloud_robustness_study import DOCS, RUNTIME, ROOT
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import read, save, paired_entries

AUDIT = DOCS/'profit-audit-v1'
KEYS = ['anchor','efficiency20','efficiency30']


def compounded(trades):
    return (exp(sum(log1p(t['return_pct']/100) for t in trades))-1)*100


def inspect_trades(trades, daily, expected_return):
    summary = summarize(trades, include_streak=True)
    actual = compounded(trades)
    assert abs(actual-expected_return) < 1e-7
    ranked = sorted(enumerate(trades),key=lambda it:it[1]['return_pct'],reverse=True)
    ranked = [(i,t) for i,t in ranked if t['return_pct'] > 0]
    sums = sum(t['return_pct'] for t in trades if t['return_pct'] > 0)
    stress = []
    for n in (1,5,10,20):
        selected = {i for i,t in ranked[:n]}
        stress.append(dict(top_winners_zeroed=n,
                           remaining_compounded_return_pct=compounded([t for i,t in enumerate(trades) if i not in selected]),
                           winning_return_share_pct=sum(t['return_pct'] for i,t in ranked[:n])/sums*100 if sums else None))
    monthly = {}
    for row in daily:
        monthly[row['date'][:7]] = row['equity']
    previous = 10000
    month_returns = []
    for month,equity in monthly.items():
        month_returns.append(dict(month=month,return_pct=(equity/previous-1)*100))
        previous=equity
    best_month=max(month_returns,key=lambda m:m['return_pct'])
    worst_month=min(month_returns,key=lambda m:m['return_pct'])
    removal_return=(exp(sum(log1p(m['return_pct']/100) for m in month_returns if m is not best_month))-1)*100
    by_exit = {reason:summarize([t for t in trades if t['exit_reason']==reason]) for reason in sorted({t['exit_reason'] for t in trades})}
    by_duration={name:summarize([t for t in trades if lower<t['duration_minutes']<=upper])
                 for name,lower,upper in [('up_to_1h',-1,60),('1h_to_4h',60,240),('4h_to_12h',240,720),('over_12h',720,float('inf'))]}
    winning_log=sum(log1p(t['return_pct']/100) for i,t in ranked)
    total_log=sum(log1p(t['return_pct']/100) for t in trades)
    running=0
    minimum=None
    for n,(i,t) in enumerate(ranked,1):
        running+=log1p(t['return_pct']/100)
        if total_log-running<=0:
            minimum=n
            break
    fields=['side','entry_time','exit_time','entry_price','exit_price','return_pct','profit','duration_minutes','exit_reason']
    return dict(summary=summary,return_pct=actual,stress=stress,
                minimum_best_winners_zeroed_to_remove_net_profit=minimum,
                side={s:summarize([t for t in trades if t['side']==s]) for s in ('long','short')},
                exit_reasons=by_exit,duration=by_duration,
                monthly_returns=month_returns,positive_months=sum(m['return_pct']>0 for m in month_returns),
                month_count=len(month_returns),best_month=best_month,worst_month=worst_month,
                best_month_zeroed_arithmetic_return_pct=removal_return,
                top_ten_trades=[{k:t[k] for k in fields} for i,t in ranked[:10]],
                longest_trade_hours=max(t['duration_minutes'] for t in trades)/60,
                average_win_log_contribution=winning_log/len(ranked) if ranked else None)


def run():
    data=read(DOCS/'results.json')
    assert data['status']=='completed'
    input_paths=[DOCS/'results.json', ROOT/'scripts/cloud_profit_audit.py',ROOT/'app/domain/backtest_diagnostics.py',
                 ROOT/'scripts/profit_protection_study.py']
    for key in KEYS:
        input_paths.extend([RUNTIME/f'{key}-full.json',RUNTIME/f'{key}-four-quarters.json'])
    provenance={p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in input_paths}
    plan=dict(created_at=datetime.now(timezone.utc).isoformat(),provenance=provenance,
              variants=KEYS,request='Fixed-parameter profit concentration, long/short contribution, months, losing trades, and exit causes.',
              rules=['No strategy changes, no new parameter candidates, no new market downloads, no fees or slippage.',
                     'Full two years and the same four-quarter following-year composition as the frozen robustness study.',
                     'Rank winning trades by per-entry percentage return, not dollar P&L distorted by compounding.',
                     'Set the best 1/5/10/20 trade returns to zero and compound the remaining sequence: arithmetic fragility check only, not a feasible strategy or a new backtest; entries/timing and other percentage returns stay fixed.',
                     'Side and exit groups attribute actual dollar P&L within the original sequence, not long-only/short-only strategy backtests.',
                     'Monthly returns use end-of-day marked account equity; first/last calendar months are partial.',
                     'Duration is observed after closing. It cannot be used as a hindsight entry filter.',
                     'No OHLC excursion inference on an intrabar exit candle; no claim about causes that this record cannot establish.',
                     'Descriptive audit only. Do not promote the retrospective candidate to a validated strategy based on this appendix.'])
    plan_path=AUDIT/'plan.json'
    if plan_path.exists():
        old=read(plan_path)
        assert old['provenance']==provenance,'Audit inputs changed; create another version'
        plan=old
    else:
        save(plan_path,plan)
        snapshot('008-fixed-profit-audit-plan',[ROOT/'scripts/cloud_profit_audit.py',plan_path])
    if (AUDIT/'results.json').exists():
        raise ValueError('Audit result already exists; do not overwrite completed audit')
    output={'plan':plan,'results':{},'matched_entries':{}}
    full={}
    for key in KEYS:
        raw=read(RUNTIME/f'{key}-full.json'); q=read(RUNTIME/f'{key}-four-quarters.json')
        full[key]=raw
        output['results'][key]={
            'full':inspect_trades(raw['trades'],data['results'][key]['full']['daily_equity'],raw['report']['return_pct']),
            'following_year':inspect_trades(q['trades'],q['daily_equity'],q['report']['return_pct'])}
    for key in KEYS[1:]:
        output['matched_entries'][key]=paired_entries(full['anchor'],full[key])
        old={(t['entry_time'],t['side']):t for t in full['anchor']['trades']}
        new={(t['entry_time'],t['side']):t for t in full[key]['trades']}
        output['matched_entries'][key]['baseline_unmatched_trade_summary']=summarize([t for k,t in old.items() if k not in new])
        output['matched_entries'][key]['candidate_unmatched_trade_summary']=summarize([t for k,t in new.items() if k not in old])
    output['status']='completed'
    save(AUDIT/'results.json',output)
    print(json.dumps({k:{p:{'return_pct':v['return_pct'],'stress':v['stress'],'summary':v['summary'],
                              'positive_months':v['positive_months'],'months':v['month_count'],'best_month':v['best_month'],
                              'worst_month':v['worst_month'],'side':v['side'],'exit':v['exit_reasons'],
                              'min_winners_zeroed':v['minimum_best_winners_zeroed_to_remove_net_profit']}
                           for p,v in item.items()} for k,item in output['results'].items()},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    run()
