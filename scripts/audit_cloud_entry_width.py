"""Describe entry-time band width versus saved trade outcomes; no strategy search."""
import argparse
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean

import numpy as np


def analyze(folder):
    result_bytes = (folder / 'result.json').read_bytes()
    result = json.loads(result_bytes)
    candles = json.loads((folder / 'data.json').read_bytes())
    times = [int(c[0]) for c in candles]
    indicators = {int(i['timestamp']): i for i in result['indicators']}
    trades = []
    for trade in result['trades']:
        index = bisect_left(times, trade['entry_time'])
        if index == 0 or index == len(times) or times[index] != trade['entry_time']:
            raise ValueError('Trade entry is not aligned to a saved candle')
        signal_time = times[index - 1]
        values = indicators[signal_time]['values']
        band_pct = 400 * values['宽度基准'] / values['中心线']
        trades.append(dict(trade_id=trade['trade_id'], signal_time=signal_time,
            entry_time=trade['entry_time'], side=trade['side'], outer_band_pct=band_pct,
            return_pct=trade['return_pct'], profit=trade['profit'], exit_reason=trade['exit_reason'],
            year=datetime.fromtimestamp(trade['entry_time']/1000, timezone.utc).year))

    ordered = sorted(trades, key=lambda t: (t['outer_band_pct'], t['trade_id']))
    buckets = [list(v) for v in np.array_split(np.array(ordered, dtype=object), 5)]

    def describe(rows):
        widths = [r['outer_band_pct'] for r in rows]
        returns = [r['return_pct'] for r in rows]
        wins = [r for r in rows if r['profit'] > 0]
        losses = [r for r in rows if r['profit'] < 0]
        return dict(count=len(rows), min_width_pct=min(widths), max_width_pct=max(widths),
            mean_width_pct=mean(widths), mean_trade_return_pct=mean(returns),
            wins=len(wins), losses=len(losses), flat=len(rows)-len(wins)-len(losses),
            win_rate_pct=100*len(wins)/len(rows),
            average_win_pct=mean(r['return_pct'] for r in wins) if wins else None,
            average_loss_pct=mean(r['return_pct'] for r in losses) if losses else None,
            initial_stop_share_pct=100*sum(r['exit_reason']=='stop_loss' for r in rows)/len(rows))

    groups = []
    grouped = defaultdict(list)
    for i, bucket in enumerate(buckets, 1):
        groups.append(dict(width_group=i, **describe(bucket)))
        for trade in bucket:
            trade['width_group'] = i
            grouped[(trade['year'], i)].append(trade)
    return dict(run_id=folder.name, source_sha256=hashlib.sha256(result_bytes).hexdigest(),
        definition='Entry signal close: (outer upper - outer lower) / EMA(hl2,55) * 100 = 4W / center * 100',
        scope='Original ETH/USDT 15m six-year saved trades; costs unchanged at zero',
        limitation='Descriptive equal-count groups based on already seen history; not a new filtered backtest, no optimized cutoff, no causal claim. Mean trade return is arithmetic per-trade return, not compounded portfolio return.',
        groups=groups, by_year=[dict(year=y, width_group=i, **describe(rows)) for (y,i),rows in sorted(grouped.items())],
        by_side=[dict(side=side, width_group=i+1, **describe([r for r in bucket if r['side']==side]))
                 for i,bucket in enumerate(buckets) for side in ('long','short')],
        trades=trades)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_folder', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = analyze(args.run_folder)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in {'trades','by_year','by_side'}}, ensure_ascii=False))
