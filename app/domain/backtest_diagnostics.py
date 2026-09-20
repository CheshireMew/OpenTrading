"""Trade-path diagnostics from saved bars and completed reverse-only trades.

Entry features use the last completed candle. Exit-open candles are excluded
from excursion measurements. Intrabar exits deliberately raise: OHLC cannot
tell which extrema occurred before such an exit.
"""
from bisect import bisect_left
from math import ceil
from statistics import mean, median


def summarize(trades, *, include_streak=False):
    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] < 0]
    gross_win = sum(t['profit'] for t in wins)
    gross_loss = -sum(t['profit'] for t in losses)
    win_return = mean(t['return_pct'] for t in wins) if wins else None
    loss_return = -mean(t['return_pct'] for t in losses) if losses else None
    streak = maximum_streak = 0
    for t in trades:
        streak = streak + 1 if t['profit'] < 0 else 0
        maximum_streak = max(streak, maximum_streak)
    report = {
        'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
        'win_rate': 100*len(wins)/len(trades) if trades else None,
        'profit': gross_win-gross_loss, 'gross_profit': gross_win, 'gross_loss': gross_loss,
        'profit_factor': gross_win/gross_loss if gross_loss else None,
        'avg_win_return_pct': win_return, 'avg_loss_return_pct': loss_return,
        'payoff_return_ratio': win_return/loss_return if win_return and loss_return else None,
        'avg_return_pct': mean(t['return_pct'] for t in trades) if trades else None,
        'breakeven_payoff_ratio': len(losses)/len(wins) if wins else None,
    }
    if include_streak:
        report['max_consecutive_losses'] = maximum_streak
    return report


def diagnose(bars, result, *, source='hl2', width_period=16, range_ema=True):
    times = [b.timestamp for b in bars]
    features = []
    base = width = atr = None
    total = 0.
    for i, bar in enumerate(bars):
        price = (bar.high+bar.low)/2 if source == 'hl2' else (bar.high+bar.low+bar.close)/3
        base = price if base is None else base+(price-base)/16
        movement = bar.high-bar.low
        tr = movement if i == 0 else max(movement, abs(bar.high-bars[i-1].close), abs(bar.low-bars[i-1].close))
        if atr is None:
            total += tr
            if i+1 == width_period:
                atr = total/width_period
        else:
            atr += (tr-atr)/width_period
        width = (movement if width is None else width+(movement-width)/16) if range_ema else atr
        er = None
        if i >= 20:
            path = sum(abs(bars[j].close-bars[j-1].close) for j in range(i-19, i+1))
            er = abs(bar.close-bars[i-20].close)/path if path else 0.
        slope = base-features[i-8]['base'] if i >= 8 else None
        features.append({'base': base, 'width': width, 'atr': atr,
                         'efficiency20': er, 'slope8': slope})
    annotated = []
    for trade in result['trades']:
        if trade['exit_phase'] == 'intrabar':
            raise ValueError('Cannot infer pre-exit extrema from an intrabar exit candle')
        a, b = bisect_left(times, trade['entry_time']), bisect_left(times, trade['exit_time'])
        if not a or a >= len(bars) or times[a] != trade['entry_time'] or b >= len(bars) or times[b] != trade['exit_time']:
            raise ValueError('Trade timestamps must match supplied bars, including a pre-entry candle')
        end = b+1 if trade['exit_phase'] == 'close' else b
        segment = bars[a:end]
        prices = [trade['entry_price'], trade['exit_price']]
        high = max(prices+[v.high for v in segment])
        low = min(prices+[v.low for v in segment])
        d, entry = trade['direction'], trade['entry_price']
        favorable = (high-entry) if d == 1 else (entry-low)
        adverse = (entry-low) if d == 1 else (high-entry)
        mfepct, maepct = 100*favorable/entry, 100*adverse/entry
        feature = features[a-1]
        close_excursion = max([0.]+[100*d*(v.close-entry)/entry for v in segment])
        annotated.append({**trade, 'mfe_pct': mfepct, 'mae_pct': maepct,
                          'max_close_profit_pct': close_excursion,
                          'giveback_pct': mfepct-trade['return_pct'],
                          'entry_efficiency20': feature['efficiency20'],
                          'entry_slope_aligned': d*feature['slope8'] > 0,
                          'entry_distance_width': d*(bars[a-1].close-feature['base'])/feature['width'],
                          'entry_atr_pct': 100*feature['atr']/bars[a-1].close})
    losses = [t for t in annotated if t['profit'] < 0]
    winners = sorted((t for t in annotated if t['profit'] > 0), key=lambda t: t['profit'], reverse=True)
    duration = {
        'up_to_1h': lambda t: t['duration_minutes'] <= 60,
        '1h_to_4h': lambda t: 60 < t['duration_minutes'] <= 240,
        '4h_to_12h': lambda t: 240 < t['duration_minutes'] <= 720,
        'over_12h': lambda t: t['duration_minutes'] > 720,
    }
    er_groups = {'below_025': lambda t: t['entry_efficiency20'] < .25,
                 '025_to_05': lambda t: .25 <= t['entry_efficiency20'] < .5,
                 'above_05': lambda t: t['entry_efficiency20'] >= .5}
    report = {
        **summarize(annotated, include_streak=True),
        'duration_groups': {k: summarize([t for t in annotated if f(t)]) for k, f in duration.items()},
        'entry_efficiency_groups': {k: summarize([t for t in annotated if f(t)]) for k, f in er_groups.items()},
        'entry_slope_groups': {str(v): summarize([t for t in annotated if t['entry_slope_aligned'] == v]) for v in (True, False)},
        'entry_distance_groups': {k: summarize([t for t in annotated if lo <= t['entry_distance_width'] < hi])
                                  for k, lo, hi in [('under_2', 0, 2), ('2_to_3', 2, 3), ('over_3', 3, float('inf'))]},
        'side': {s: summarize([t for t in annotated if t['side'] == s]) for s in ('long', 'short')},
        'losses_previously_up': {str(level): {
            'intrabar_count': sum(t['mfe_pct'] >= level for t in losses),
            'at_close_count': sum(t['max_close_profit_pct'] >= level for t in losses),
            'loss_count': len(losses)} for level in (.5, 1., 2.)},
        'losses_never_up_05_pct': sum(t['mfe_pct'] < .5 for t in losses),
        'median_winner_giveback_pct': median(t['giveback_pct'] for t in winners) if winners else None,
        'top_5pct_winners_gross_profit_share_pct': 100*sum(t['profit'] for t in winners[:ceil(len(winners)*.05)])/sum(t['profit'] for t in winners) if winners else None,
    }
    return {'report': report, 'trades': annotated}
