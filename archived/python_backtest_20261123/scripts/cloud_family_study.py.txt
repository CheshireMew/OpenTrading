"""Compare screenshot hypotheses using a saved OpenTrading run, without fetching data.

Run with ``python -m scripts.cloud_family_study`` from the project root.
This is an in-sample identification study, not a new trading strategy or proof
of the screenshot author's implementation. Geometry is ranked before signals.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd
import talib

from app.domain.signal_comparison import compare_cloud, compare_signals
from app.domain.local_backtest import Bar, BarResult, Intent, TrendCloud, simulate
from app.services.local_backtest_strategies import digest
from strategies.adaptive_cloud import Rma


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = 'bd9ce7f3f6224eb4bf0fda53bae301f6'
STUDY = ROOT / 'docs/verification/eth-cloud-202608'


def ma(x, kind, n):
    s = pd.Series(x)
    if kind == 'EMA':
        return s.ewm(span=n, adjust=False).mean().to_numpy()
    if kind == 'RMA':
        seed = np.full(len(x), np.nan)
        seed[n-1] = np.mean(x[:n])
        seed[n:] = x[n:]
        return pd.Series(seed).ewm(alpha=1/n, adjust=False).mean().to_numpy()
    if kind == 'SMA':
        return s.rolling(n).mean().to_numpy()
    if kind == 'WMA':
        return talib.WMA(x, n)
    if kind == 'DEMA':
        e = ma(x, 'EMA', n)
        return 2*e-ma(e, 'EMA', n)
    if kind == 'TEMA':
        e = ma(x, 'EMA', n)
        ee = ma(e, 'EMA', n)
        return 3*e-3*ee+ma(ee, 'EMA', n)
    if kind == 'HMA':
        fast = x if n//2 == 1 else talib.WMA(x, n//2)
        h = 2*fast-talib.WMA(x, n)
        smooth = int(np.sqrt(n))
        return h if smooth == 1 else talib.WMA(h, smooth)
    if kind == 'KAMA':
        return talib.KAMA(x, n)
    raise ValueError(kind)


class Geometry:
    def __init__(self, times, reference):
        self.times, self.reference = times, reference
        self.a, self.b = reference['price_to_pixel_log']
        self.samples = reference['cloud_samples']
        self.st = np.array([s['timestamp'] for s in self.samples])
        self.left = np.searchsorted(times, self.st, side='right')-1
        self.right = self.left+1
        if np.any(self.left < 0) or np.any(self.right >= len(times)):
            raise ValueError('Reference samples outside saved snapshot')
        self.f = (self.st-times[self.left])/(times[self.right]-times[self.left])
        self.target = np.array([[s['upper_y'], s['lower_y']] for s in self.samples])

    def at(self, x):
        return x[self.left]*(1-self.f)+x[self.right]*self.f

    def error(self, center, width, multiplier):
        upper, lower = center+multiplier*width, center-multiplier*width
        if np.any(lower[self.left] <= 0) or np.any(lower[self.right] <= 0):
            return np.inf
        y = np.stack([self.at(self.a*np.log(v)+self.b) for v in (upper, lower)], axis=1)
        return float(np.sqrt(np.mean((y-self.target)**2)))

    def fit_width(self, center, width):
        # The linearized log projection gives the bracket; optimize the actual
        # log-pixel residual inside it. No signal locations enter this fit.
        unit = -self.a*self.at(width/center)
        target_half = (self.target[:, 1]-self.target[:, 0])/2
        k = float(np.dot(unit, target_half)/np.dot(unit, unit))
        lo, hi = max(0., k*.5), k*1.5
        for _ in range(24):
            p, q = lo+(hi-lo)/3, hi-(hi-lo)/3
            if self.error(center, width, p) < self.error(center, width, q):
                hi = q
            else:
                lo = p
        k = (lo+hi)/2
        return self.error(center, width, k), k


class FixedCross:
    """Sequential counterexample; receives only the project's past-bar API."""
    def __init__(self, use_true_range):
        self.use_true_range = use_true_range
        self.processed, self.base, self.previous = 0, None, None
        self.previous_upper, self.previous_lower = None, None
        self.width = Rma(14)

    def on_bar(self, context):
        result = None
        for bar in context.history[self.processed:]:
            src = (bar.high+bar.low+bar.close)/3
            self.base = src if self.base is None else self.base+(src-self.base)/16
            movement = bar.high-bar.low
            if self.use_true_range and self.previous is not None:
                movement = max(movement, abs(bar.high-self.previous), abs(bar.low-self.previous))
            width = self.width.update(movement)
            result = None
            if width is not None:
                upper, lower = self.base+.99*width, self.base-.99*width
                long = self.previous_upper is not None and self.previous <= self.previous_upper and bar.close > upper
                short = self.previous_lower is not None and self.previous >= self.previous_lower and bar.close < lower
                result = BarResult(intent=Intent('long' if long else 'short') if long or short else None,
                                   cloud=TrendCloud(self.base+.45*width, self.base-.45*width, bar.close > self.base))
                self.previous_upper, self.previous_lower = upper, lower
            self.previous = bar.close
            self.processed += 1
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', default=DEFAULT_RUN)
    parser.add_argument('--reference', type=Path, default=STUDY/'reference.json')
    parser.add_argument('--output', type=Path, default=STUDY/'cloud-family-study.json')
    args = parser.parse_args()
    folder = ROOT/'.opentrading_runtime/local_backtests'/args.run
    metadata = json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    raw = (folder/'data.json').read_bytes()
    if digest(raw) != metadata['data_hash']:
        raise ValueError('OpenTrading snapshot hash mismatch')
    config = json.loads((folder/'config.json').read_text(encoding='utf-8'))
    data = np.array(json.loads(raw), dtype=float)
    times, o, h, l, c, volume = data.T
    if not np.all(np.diff(times) == 900000):
        raise ValueError('Study requires a complete 15m snapshot')
    start = datetime.fromisoformat(config['start'].replace('Z', '+00:00')).timestamp()*1000
    main_mask = times >= start
    reference = json.loads(args.reference.read_text(encoding='utf-8'))
    geo = Geometry(times, reference)
    sources = {'close': c, 'open': o, 'high': h, 'low': l, 'hl2': (h+l)/2,
               'hlc3': (h+l+c)/3, 'ohlc4': (o+h+l+c)/4}
    tr = np.maximum.reduce([h-l, np.abs(h-np.r_[c[0], c[:-1]]), np.abs(l-np.r_[c[0], c[:-1]])])
    widths = {'ATR': [(n, ma(tr, 'RMA', n)) for n in range(2, 61)],
              'RMA(high-low)': [(n, ma(h-l, 'RMA', n)) for n in range(2, 61)],
              'SMA(high-low)': [(n, ma(h-l, 'SMA', n)) for n in range(2, 61)],
              'rolling_std(close)': [(n, pd.Series(c).rolling(n).std(ddof=0).to_numpy()) for n in range(2, 61)]}
    records, arrays, center_results = {}, {}, []

    def keep(family, parameters, center, width, multiplier=None):
        rmse, k = geo.fit_width(center, width) if multiplier is None else (geo.error(center, width, multiplier), multiplier)
        if not np.isfinite(rmse):
            return
        if family not in records or rmse < records[family]['rmse_px']:
            records[family] = {'family': family, 'parameters': parameters, 'width_multiplier': k, 'rmse_px': rmse}
            arrays[family] = (center, width, k)

    kinds = ('EMA', 'RMA', 'SMA', 'WMA', 'DEMA', 'TEMA', 'HMA', 'KAMA')
    for kind in kinds:
        ranked = []
        for source, values in sources.items():
            for n in range(2, 101):
                center = ma(values, kind, n)
                center_rmse = float(np.sqrt(np.mean((geo.at(geo.a*np.log(center)+geo.b)-geo.target.mean(axis=1))**2)))
                if np.isfinite(center_rmse):
                    ranked.append((center_rmse, source, n, center))
        ranked.sort(key=lambda v:v[0])
        center_results.append({'kind': kind, 'source': ranked[0][1], 'length': ranked[0][2], 'center_rmse_px': ranked[0][0]})
        # Width is much smaller than center movement. Keep three best center
        # fits per smoother; this staged search is not an exhaustive proof.
        for _, source, n, center in ranked[:3]:
            for width_kind, options in widths.items():
                for wn, width in options:
                    keep(f'{kind} + {width_kind}', {'source': source, 'length': n, 'width_length': wn}, center, width)
            keep(f'{kind} percentage envelope', {'source': source, 'length': n}, center, center)
        for n in range(2, 101):
            upper, lower = ma(h, kind, n), ma(l, kind, n)
            center, width = (upper+lower)/2, np.abs(upper-lower)/2
            keep(f'{kind}(high/low) channel', {'length': n}, center, width, 1.)
            keep(f'{kind}(high/low) scaled channel', {'length': n}, center, width)
        print(f'Compared {kind}', flush=True)

    # Natural, unscaled dual-MA bands and Donchian channels are separate
    # explanations; their centers are not chosen from the symmetric-band fit.
    for kind in ('EMA', 'SMA'):
        for source in ('close', 'hl2', 'hlc3', 'ohlc4'):
            values = {n: ma(sources[source], kind, n) for n in range(2, 101)}
            for fast in range(2, 100):
                for slow in range(fast+1, 101):
                    center = (values[fast]+values[slow])/2
                    width = np.abs(values[fast]-values[slow])/2
                    keep(f'dual {kind} band', {'source': source, 'fast': fast, 'slow': slow}, center, width, 1.)
    for n in range(2, 101):
        upper, lower = pd.Series(h).rolling(n).max().to_numpy(), pd.Series(l).rolling(n).min().to_numpy()
        keep('Donchian channel', {'length': n}, (upper+lower)/2, (upper-lower)/2, 1.)

    # Fixed prior candidate and a no-ATR counterexample, with no retuning.
    base = ma(sources['hlc3'], 'EMA', 31)
    keep('prior candidate (fixed)', {'source': 'hlc3', 'length': 31, 'width_length': 14}, base, ma(tr, 'RMA', 14), .45)
    keep('same candidate using high-low (fixed)', {'source': 'hlc3', 'length': 31, 'width_length': 14}, base, ma(h-l, 'RMA', 14), .45)

    for family, rec in records.items():
        center, width, k = arrays[family]
        observations = [{'timestamp': int(t), 'cloud': {'upper': float(b+k*w), 'lower': float(b-k*w)}}
                        for t, b, w in zip(times[main_mask], center[main_mask], width[main_mask])]
        measured = compare_cloud(observations, reference, 900000)
        if abs(measured['rmse_px']-rec['rmse_px']) > 1e-8 or measured['unavailable_count']:
            raise AssertionError('Vector search differs from project comparison')
        rec['comparison'] = {k: v for k, v in measured.items() if k != 'samples'}
        # Descriptive regional errors, not held-out validation: all sampled
        # regions were already used to choose the geometry.
        rec['regional_rmse_px'] = [float(np.sqrt(np.mean([s[key]**2 for s in chunk for key in ('upper_error_px', 'lower_error_px')])))
                                  for chunk in np.array_split(measured['samples'], 3)]

    # Apply exactly the already proposed crossing threshold to two widths.
    signal_checks = []
    bars = [Bar(int(row[0]), *map(float, row[1:])) for row in data]
    warmup = int((~main_mask).sum())
    validation = {'snapshot_hash': True, 'geometry_families_checked_by_project_comparator': len(records)}
    for name, width in [('ATR(14)', ma(tr, 'RMA', 14)), ('RMA(high-low,14)', ma(h-l, 'RMA', 14))]:
        upper, lower = base+.99*width, base-.99*width
        longs = (c[1:] > upper[1:]) & (c[:-1] <= upper[:-1])
        shorts = (c[1:] < lower[1:]) & (c[:-1] >= lower[:-1])
        signals = [{'timestamp': int(times[i]), 'action': action} for i in range(1, len(c)) if main_mask[i]
                   for action, mask in [('long', longs), ('short', shorts)] if mask[i-1]]
        use_tr = name == 'ATR(14)'
        sequential = simulate(bars, FixedCross(use_tr), {}, warmup=warmup, step_ms=900000)
        if [(s['timestamp'], s['action']) for s in sequential['signals']] != [(s['timestamp'], s['action']) for s in signals]:
            raise AssertionError('Vector crossing differs from project simulator')
        sequential['run'] = {'id': args.run, 'config': config}
        result = compare_signals(sequential, reference, 900000)
        prefix = simulate(bars[:750], FixedCross(use_tr), {}, warmup=warmup, step_ms=900000)
        if prefix['indicators'] != sequential['indicators'][:750-warmup]:
            raise AssertionError('Prefix observations changed after adding future bars')
        signal_checks.append({'width': name, 'sequential_project_simulation': True, 'prefix_observations_equal': True,
                              **{k: result[k] for k in ('actual_count', 'matched_count', 'missing_count', 'extra_count', 'all_signals_match')},
                              'cloud_rmse_px': result['cloud_comparison']['rmse_px']})
        if use_tr:
            saved = json.loads((folder/'result.json').read_text(encoding='utf-8'))
            if len(saved['indicators']) != len(sequential['indicators']):
                raise AssertionError('Different saved observation count')
            max_error = max(abs(a['cloud'][edge]-b['cloud'][edge]) for a, b in zip(saved['indicators'], sequential['indicators']) for edge in ('upper', 'lower'))
            if max_error > 1e-8:
                raise AssertionError('Prior candidate differs from saved run')
            validation['prior_candidate_max_difference_from_saved_run_price'] = max_error

    output = {'run_id': args.run, 'data_hash': digest(raw), 'reference_hash': digest(args.reference.read_bytes()),
              'source': metadata['source'], 'scope': 'Same-image geometry search; not blind, not out-of-sample, not original-source identification. No downloads.',
              'search': {'sources': list(sources), 'smoothers': list(kinds), 'center_lengths': [2, 100], 'width_lengths': [2, 60],
                         'center_selection': 'Keep 3 smallest center-line errors for each smoother, then fit widths; not exhaustive.',
                         'width_fit': 'One constant nonnegative multiplier, actual log-pixel residual; natural channels fix it at 1.',
                         'signal_use': 'No signals used to rank geometry; fixed prior signal rule checked only for ATR vs high-low replacement.',
                         'not_scored': 'Color switches, covered parts, bottom horizontal fill, text, unfinished last bar.'},
              'best_center_per_smoother': sorted(center_results, key=lambda r:r['center_rmse_px']),
              'families': sorted(records.values(), key=lambda r:r['rmse_px']),
              'true_range_vs_high_low': {'main_bars': int(main_mask.sum()), 'different_bars': int(np.sum(np.abs(tr[main_mask]-(h-l)[main_mask]) > 1e-8)),
                                         'max_difference': float(np.max(np.abs(tr[main_mask]-(h-l)[main_mask]))),
                                         'max_smoothed_difference': float(np.max(np.abs(ma(tr, 'RMA', 14)[main_mask]-ma(h-l, 'RMA', 14)[main_mask])))},
              'fixed_cross_signal_checks': signal_checks, 'validation': validation}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'centers': output['best_center_per_smoother'], 'best_families': output['families'][:8],
                      'range_difference': output['true_range_vs_high_low'], 'signals': signal_checks}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
