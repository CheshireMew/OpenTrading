"""Descriptive decomposition of saved trades, using project attribution math.

No strategy is run; a winners-only account is retrospective perfect selection.
"""
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
from math import ceil, exp, isclose, log1p
from pathlib import Path
import csv
import gzip
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from app.domain.cloud_trade_attribution import compound, summary

OUT = Path(__file__).resolve().parent


def read(path):
    opener = gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8') as f:
        return json.load(f)


def digest(path):
    h=sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def loss_kind(t,step):
    if t['return_pct']>=0:
        return 'winner' if t['return_pct']>0 else 'flat'
    if t['exit_reason'] in ('signal','reversal'):
        return 'reverse_within_4_periods' if t['duration_minutes']<=4*step else 'other_reverse'
    return t['exit_reason'] if t['exit_reason'] in ('stop_loss','profit_protection') else 'other_loss'


def main():
    plan=read(OUT/'plan.json')
    rows=[]
    for selection in plan['selection']:
        path=ROOT/selection['path'];result=read(path)
        trades=result['trades'];report=result['report']
        s=summary(trades)
        assert isclose(report['return_pct'],selection['expected_return'],rel_tol=1e-9)
        assert isclose(s['compound_return_pct'],report['return_pct'],rel_tol=1e-9)
        assert len(trades)==report['total_trades']
        assert (s['wins'],s['losses'],s['flat'])==(report['wins'],report['losses'],report['breakeven'])
        assert all((t['profit']>0)==(t['return_pct']>0) and (t['profit']<0)==(t['return_pct']<0) for t in trades)
        winners=[t for t in trades if t['return_pct']>0]
        losers=[t for t in trades if t['return_pct']<0]
        win_sum=sum(t['return_pct'] for t in winners)
        loss_sum=-sum(t['return_pct'] for t in losers)
        win_log=sum(log1p(t['return_pct']/100) for t in winners)
        loss_log=sum(log1p(t['return_pct']/100) for t in losers)
        only_wins=compound([t['return_pct'] for t in winners])
        assert isclose(exp(win_log+loss_log),1+report['return_pct']/100,rel_tol=1e-9)
        assert isclose(win_sum-loss_sum,s['sum_trade_return_pct'],abs_tol=1e-7)
        top_count=max(1,ceil(len(winners)*.1))
        top=sorted(winners,key=lambda t:t['return_pct'],reverse=True)[:top_count]
        years=(datetime.fromisoformat(selection['period'][1])-datetime.fromisoformat(selection['period'][0])).days/365.2425
        step={'15m':15,'30m':30,'1h':60,'4h':240}[selection['timeframe']]
        groups=defaultdict(list)
        for t in trades:groups[loss_kind(t,step)].append(t)
        loss_groups={k:dict(count=len(v),sum_loss_pct=-sum(t['return_pct'] for t in v),
                      share_of_loss_count_pct=len(v)/len(losers)*100,
                      share_of_equal_stake_loss_pct=-sum(t['return_pct'] for t in v)/loss_sum*100)
                     for k,v in groups.items() if k not in ('winner','flat')}
        assert sum(g['count'] for g in loss_groups.values())==len(losers)
        side_stats={side:summary([t for t in trades if t['side']==side]) for side in ('long','short')}
        row=dict(selection=selection,source_sha256=digest(path),original_report=report,
            all_trade_statistics=s,winning_trade_statistics=summary(winners),losing_trade_statistics=summary(losers),
            winners_only_return_pct=only_wins,winners_only_final_equity=10000*(1+only_wins/100),
            winners_only_growth_factor=exp(win_log),losses_growth_factor=exp(loss_log),
            equal_stake_10000=dict(gross_profit=win_sum*100,gross_loss=loss_sum*100,
                net_profit=(win_sum-loss_sum)*100,loss_absorption_pct=loss_sum/win_sum*100,
                gross_profit_per_year=win_sum*100/years,net_profit_per_year=(win_sum-loss_sum)*100/years),
            years=years,trades_per_year=len(trades)/years,winners_per_year=len(winners)/years,
            largest_win_pct=max(t['return_pct'] for t in winners),
            top_10pct_winner_count=top_count,
            top_10pct_winner_profit_share_pct=sum(t['return_pct'] for t in top)/win_sum*100,
            missing_winners_allowance_per_10_saved_losses=10*(-s['mean_loss_pct'])/s['mean_win_pct'],
            loss_categories=loss_groups,by_side=side_stats)
        rows.append(row)
        fields=['trade_id','side','entry_time','exit_time','entry_price','exit_price',
                'return_pct','duration_minutes','exit_reason','entry_bar_ambiguous','loss_category',
                'equal_stake_profit','kept_in_winners_only']
        with (OUT/f"{selection['asset'].lower()}-trades.csv").open('x',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
            for t in trades:
                entry={k:t.get(k) for k in fields}
                entry.update(loss_category=loss_kind(t,step),equal_stake_profit=t['return_pct']*100,
                             kept_in_winners_only=t['return_pct']>0)
                writer.writerow(entry)
        print(selection['asset'],json.dumps({k:row[k] for k in ['winners_only_return_pct','equal_stake_10000','top_10pct_winner_profit_share_pct','missing_winners_allowance_per_10_saved_losses','loss_categories']},ensure_ascii=False),flush=True)
        del result,trades,winners,losers,top,groups
    output=dict(scope=plan['scope'],calculations=plan['calculations'],rows=rows,
                verification='Saved original return and counts match; per-trade compound, additive and log-factor identities verified for all six.')
    with (OUT/'results.json').open('x',encoding='utf-8') as f:
        json.dump(output,f,ensure_ascii=False,indent=2)


if __name__=='__main__':main()
