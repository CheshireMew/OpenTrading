"""Descriptive attribution of fixed cloud strategies; never selects parameters.

Calendar returns are marked equity, not exit-year cash profits. Trade groups
use equal-entry percentage and log returns so compounding does not overweight
late trades. Features use only the last observed completed pre-entry candle.
"""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from math import expm1, log1p, isclose, ceil
import numpy as np

DAY = 86400000


def date(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).isoformat()


def compound(returns):
    return 100 * expm1(sum(log1p(float(r) / 100) for r in returns))


def summary(trades):
    r = np.array([t['return_pct'] for t in trades], dtype=float)
    w, l = r[r > 0], r[r < 0]
    hours = np.array([t['duration_minutes'] / 60 for t in trades])
    ratio = float(w.mean() / -l.mean()) if len(w) and len(l) else None
    streak = maximum = 0
    for x in r:
        streak = streak + 1 if x < 0 else 0
        maximum = max(maximum, streak)
    return dict(trades=len(r), wins=len(w), losses=len(l), flat=int(sum(r == 0)),
        win_rate=100 * len(w) / len(r) if len(r) else None,
        mean_return_pct=float(r.mean()) if len(r) else None,
        mean_win_pct=float(w.mean()) if len(w) else None,
        mean_loss_pct=float(l.mean()) if len(l) else None,
        win_loss_size_ratio=ratio, breakeven_size_ratio=len(l)/len(w) if len(w) else None,
        equal_principal_profit_factor=float(w.sum() / -l.sum()) if len(l) else None,
        sum_trade_return_pct=float(r.sum()), log_growth=sum(log1p(float(x)/100) for x in r),
        compound_return_pct=compound(r), actual_cash_profit=sum(t['profit'] for t in trades),
        mean_hours=float(hours.mean()) if len(r) else None,
        median_hours=float(np.median(hours)) if len(r) else None,
        p90_hours=float(np.quantile(hours, .9)) if len(r) else None,
        maximum_hours=float(hours.max()) if len(r) else None,
        max_loss_streak=maximum)


def group(trades, field):
    buckets = defaultdict(list)
    for t in trades:
        buckets[str(t[field])].append(t)
    return {k: summary(v) for k, v in sorted(buckets.items())}


def ema(values, n):
    out = np.empty(len(values)); value = float(values[0]); alpha = 2/(n+1)
    for i, v in enumerate(values):
        value += alpha*(v-value); out[i] = value
    return out


def rolling_efficiency(close, n):
    changes = np.concatenate(([0.], np.cumsum(np.abs(np.diff(close)))))
    out = np.full(len(close), np.nan)
    path = changes[n:] - changes[:-n]
    out[n:] = np.divide(np.abs(close[n:] - close[:-n]), path, out=np.zeros(len(path)), where=path > 0)
    return out


def features(rows, parameters):
    a = np.array(rows, dtype=float); times = a[:, 0].astype('int64')
    o, h, l, c, v = [a[:, i] for i in range(1, 6)]
    center = ema((h+l)/2, parameters['center_length'])
    width = ema(h-l, parameters['width_length'])
    er = rolling_efficiency(c, 96)
    prev30 = np.searchsorted(times, times-30*DAY, side='right')-1
    mom30 = np.full(len(c), np.nan)
    valid = prev30 >= 0; mom30[valid] = 100*(c[valid]/c[prev30[valid]]-1)
    body = np.divide(np.abs(c-o), h-l, out=np.zeros(len(c)), where=h > l)
    volsum = np.concatenate(([0.], np.cumsum(v)))
    volratio = np.full(len(c), np.nan)
    previous = (volsum[20:-1]-volsum[:-21])/20
    volratio[20:] = np.divide(v[20:], previous, out=np.zeros(len(previous)), where=previous > 0)
    distance = np.divide(c-center, width, out=np.zeros(len(c)), where=width > 0)
    upper, lower = center+parameters['trigger_mult']*width, center-parameters['trigger_mult']*width
    crosses = np.zeros(len(c), dtype=int)
    crosses[1:][(c[:-1] <= upper[:-1]) & (c[1:] > upper[1:])] = 1
    crosses[1:][(c[:-1] >= lower[:-1]) & (c[1:] < lower[1:])] = -1
    blocked = (crosses != 0) & (np.abs(distance) > parameters['chase_mult'])
    return dict(times=times, close=c, width_pct=width/c*100, efficiency96=er,
                momentum30=mom30, body=body, volume_ratio=volratio, distance=distance,
                crosses=crosses, blocked=blocked, volume=v)


def bucket(value, cuts, names):
    if not np.isfinite(value): return 'insufficient_history'
    return names[bisect_right(cuts, value)]


def annotate(trades, f, parameters):
    out = []
    for t in trades:
        i = bisect_left(f['times'], t['entry_time'])-1
        assert i >= 0 and f['times'][i] < t['entry_time']
        width = f['width_pct'][i]
        record = dict(t, signal_time=int(f['times'][i]), width_pct=float(width),
            entry_efficiency96=float(f['efficiency96'][i]),
            entry_distance=float(abs(f['distance'][i])),
            activation_widths=float(parameters['activation_pct']/width) if width else None,
            stop_widths=float(parameters['initial_stop_pct']/width) if width else None,
            volatility=bucket(width, [.15, .4], ['below_015', '015_to_04', 'above_04']),
            efficiency=bucket(f['efficiency96'][i], [.1, .25], ['below_01', '01_to_025', 'above_025']),
            momentum30=bucket(f['momentum30'][i], [-10, 10], ['down_10', 'between_10', 'up_10']),
            body=bucket(f['body'][i], [1/3, 2/3], ['small', 'medium', 'large']),
            volume_bucket=bucket(f['volume_ratio'][i], [1, 2], ['below_1', '1_to_2', 'above_2']),
            zero_volume=bool(f['volume'][i] == 0),
            duration=bucket(t['duration_minutes']/60, [1, 4, 12, 24], ['under_1h','1_to_4h','4_to_12h','12_to_24h','over_24h']))
        # Peak is engine-recorded before the exit, not the whole exit candle high/low.
        peak = t.get('profit_peak_pct', 0.)
        record['recorded_peak_bucket'] = bucket(peak, [.5, 1, parameters['activation_pct']],
                                                ['under_05', '05_to_1', '1_to_activation', 'activated_level'])
        out.append(record)
    return out


def calendar_returns(equity, rows, boundaries):
    et = [x['timestamp'] for x in equity]; ev = [x['equity'] for x in equity]
    bt = [r[0] for r in rows]; close = [r[4] for r in rows]
    result = []
    for label, start, end in boundaries:
        if end <= et[0] or start >= et[-1]: continue
        start, end = max(start, et[0]), min(end, et[-1])
        i, j = bisect_right(et, start)-1, bisect_right(et, end)-1
        initial, final = ev[i], ev[j]
        # First period starts at first candle open; later boundaries use prior close.
        pi = bisect_left(bt, start)-1; pj = bisect_left(bt, end)-1
        p0 = rows[bisect_left(bt, start)][1] if start == et[0] else close[pi]
        p1 = close[pj]
        prices = np.array([p0]+close[pi+1:pj+1])
        path = float(np.abs(np.diff(np.log(prices))).sum())
        efficiency = abs(float(np.log(p1/p0)))/path if path else 0
        dd = 100*float(np.max(1-prices/np.maximum.accumulate(prices)))
        result.append(dict(label=label, start=start, end=end, start_equity=initial, end_equity=final,
            return_pct=100*(final/initial-1), market_return_pct=100*(p1/p0-1),
            market_max_drawdown_pct=dd, market_path_efficiency=efficiency))
    assert isclose(compound(x['return_pct'] for x in result), 100*(ev[-1]/ev[0]-1), abs_tol=1e-6, rel_tol=1e-9)
    return result


def periods(start, end, kind):
    ds = datetime.fromtimestamp(start/1000, timezone.utc); de = datetime.fromtimestamp(end/1000, timezone.utc)
    stamp = lambda y,m,d: int(datetime(y,m,d,tzinfo=timezone.utc).timestamp()*1000)
    if kind == 'year':
        return [(str(y), stamp(y,1,1), stamp(y+1,1,1)) for y in range(ds.year, de.year+1)]
    if kind == 'anniversary':
        return [(f'{y}-09→{y+1}-09',stamp(y,9,10),stamp(y+1,9,10)) for y in range(ds.year, de.year)]
    return [(f'{y}-{m:02}',stamp(y,m,1),stamp(y+(m==12),m%12+1,1))
            for y in range(ds.year,de.year+1) for m in range(1,13)]


def stress(trades, months):
    returns = [t['return_pct'] for t in trades]
    winners = sorted([x for x in returns if x > 0], reverse=True)
    total_log = sum(log1p(x/100) for x in returns)
    winning_log = sum(log1p(x/100) for x in winners)
    loss_of_edge, acc = None, 0
    for i,x in enumerate(winners,1):
        acc += log1p(x/100)
        if total_log > 0 and acc >= total_log:
            loss_of_edge = i; break
    checks=[]
    for label,n in [('top_10',10),('top_1pct_winners',ceil(.01*len(winners))),('top_5pct_winners',ceil(.05*len(winners)))]:
        removed=sum(log1p(x/100) for x in winners[:n])
        checks.append(dict(label=label,trades=min(n,len(winners)),return_if_zero_pct=100*expm1(total_log-removed),
                           gross_winning_log_share_pct=100*removed/winning_log if winning_log else None))
    best=sorted(months,key=lambda m:m['return_pct'],reverse=True)
    return dict(trade_checks=checks,best_winners_zeroed_to_erase_profit=loss_of_edge,
        best_months=best[:10],worst_months=best[-5:][::-1],
        best_month_zeroed_pct=compound(m['return_pct'] for m in months if m != best[0]),
        best_three_months_zeroed_pct=compound(m['return_pct'] for m in months if m not in best[:3]))


def analyze(trace, rows):
    p=trace['parameters']; f=features(rows,p); ts=annotate(trace['trades'],f,p)
    all_summary=summary(ts)
    assert isclose(all_summary['compound_return_pct'],trace['report']['return_pct'],abs_tol=1e-6,rel_tol=1e-9)
    start,end=trace['equity'][0]['timestamp'],trace['equity'][-1]['timestamp']
    years=calendar_returns(trace['equity'],rows,periods(start,end,'year'))
    anniversaries=calendar_returns(trace['equity'],rows,periods(start,end,'anniversary'))
    months=calendar_returns(trace['equity'],rows,periods(start,end,'month'))
    for year in years+anniversaries:
        yr=[t for t in ts if year['start'] <= t['exit_time'] < year['end']]
        year['closed_trades']=summary(yr);year['side']=group(yr,'side');year['exits']=group(yr,'exit_reason')
    losses=[t for t in ts if t['return_pct'] < 0];wins=[t for t in ts if t['return_pct'] > 0]
    active=sum(t.get('protection_active',False) for t in ts)
    valid=(f['times']>=start)&(f['times']<end)
    def clean_trade(t):
        return {k:t[k] for k in ('side','entry_time','exit_time','entry_price','exit_price','return_pct','duration_minutes','exit_reason','profit_peak_pct','width_pct','entry_efficiency96','entry_distance')}
    quick=sum(t['return_pct']<0 and t['exit_reason'] in ('reversal','signal') and t['duration_minutes']<=240 for t in ts)
    growth=sum(log1p(t['return_pct']/100) for t in ts)
    arithmetic=sum(t['return_pct']/100 for t in ts)
    output=dict(parameters=p,period=trace['period'],summary=all_summary,side=group(ts,'side'),
        exits=group(ts,'exit_reason'),loss_exits=group(losses,'exit_reason'),duration=group(ts,'duration'),
        winners=summary(wins),losers=summary(losses),years=years,anniversary_years=anniversaries,months=months,
        stress=stress(ts,months),market=calendar_returns(trace['equity'],rows,[('full',start,end)])[0],
        entry_groups={field:group(ts,field) for field in ('volatility','efficiency','momentum30','body','volume_bucket','zero_volume')},
        entry_momentum_side={s:group([t for t in ts if t['side']==s],'momentum30') for s in ('long','short')},
        loss_path=dict(total=len(losses),quick_opposite_losses=quick,
            recorded_peak_under_05=sum(t.get('profit_peak_pct',0)<.5 for t in losses),
            activated_but_lost=sum(t.get('protection_active',False) for t in losses),
            recorded_peak_buckets=group(losses,'recorded_peak_bucket')),
        scale=dict(median_entry_width_pct=float(np.median([t['width_pct'] for t in ts])),
            median_activation_widths=float(np.median([t['activation_widths'] for t in ts if t['activation_widths'] is not None])),
            activation_trades=active,activation_rate_pct=100*active/len(ts),
            raw_crossings=int(sum(f['crosses'][valid]!=0)),distance_blocked=int(sum(f['blocked'][valid])),
            zero_volume_signals=sum(t['zero_volume'] for t in ts)),
        compounding=dict(sum_returns_pct=arithmetic*100,log_growth=growth,volatility_drag_log=arithmetic-growth),
        top_trades=[clean_trade(t) for t in sorted(ts,key=lambda t:t['return_pct'],reverse=True)[:20]],
        worst_trades=[clean_trade(t) for t in sorted(ts,key=lambda t:t['return_pct'])[:10]])
    assert sum(x['trades'] for x in output['side'].values())==len(ts)
    assert isclose(sum(x['log_growth'] for x in output['side'].values()),growth,abs_tol=1e-9)
    return output


def monthly_relationship(a,b):
    am={x['label']:x for x in a['months']};bm={x['label']:x for x in b['months']};months=sorted(set(am)&set(bm))
    ac=np.array([log1p(am[m]['return_pct']/100) for m in months]);bc=np.array([log1p(bm[m]['return_pct']/100) for m in months])
    ap=np.array([log1p(am[m]['market_return_pct']/100) for m in months]);bp=np.array([log1p(bm[m]['market_return_pct']/100) for m in months])
    at=sorted(months,key=lambda m:am[m]['return_pct'],reverse=True)[:10];bt=sorted(months,key=lambda m:bm[m]['return_pct'],reverse=True)[:10]
    return dict(months=len(months),strategy_correlation=float(np.corrcoef(ac,bc)[0,1]),
        market_correlation=float(np.corrcoef(ap,bp)[0,1]),top10_overlap=sorted(set(at)&set(bt)),
        both_positive_months=int(sum((ac>0)&(bc>0))),both_negative_months=int(sum((ac<0)&(bc<0))))
