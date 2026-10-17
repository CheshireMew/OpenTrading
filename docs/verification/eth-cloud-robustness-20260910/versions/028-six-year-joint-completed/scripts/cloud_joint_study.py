"""All 128 predeclared combinations on six years, using the project simulator."""
import argparse
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import product
from math import prod
from statistics import median
import json

from app.domain.local_backtest import simulate
from app.domain.backtest_history import validate_observed_bars
from app.services.local_backtest_strategies import digest, environment, load_strategy, validate_parameters
from app.contracts.local_backtest import LocalBacktestCommand
from app.services.local_backtest_service import LocalBacktestService
from app.infra.db import build_database_runtime
from config import settings
from scripts.profit_protection_study import ROOT, read, save, metrics
from scripts.cloud_strategy_versions import snapshot
from scripts.trend_cloud_study import stamp

DOCS = ROOT/'docs/verification/eth-cloud-joint-six-year-20260911'
RUNTIME = ROOT/'.heimdall_runtime/cloud-joint-six-year-20260911'
SOURCE = ROOT/'strategies/trend_cloud_parameters_v4.py'
OLD = ROOT/'docs/verification/eth-cloud-parameters-20260910'
AXES = {'center_length': [55, 65], 'width_length': [31, 40], 'trigger_mult': [.4, .8],
        'chase_mult': [2., 2.5], 'activation_pct': [2., 3.], 'giveback_pct': [40., 50.], 'initial_stop_pct': [0., 1.]}
LABELS = {'center_length': '中心线周期', 'width_length': '振幅平均周期', 'trigger_mult': '突破门槛 / W',
          'chase_mult': '最远入场距离 / W', 'activation_pct': '启动保护的浮盈 %', 'giveback_pct': '允许回吐 %', 'initial_stop_pct': '初始止损 %'}


def token(p):
    return tuple(p[k] for k in sorted(p) if k != 'record_indicators')


def variant_key(p):
    return '_'.join(f'{prefix}{p[field]:g}' for prefix, field in zip(['c', 'w', 't', 'd', 'a', 'g', 's'], AXES)).replace('.', 'p')


def combinations():
    _, spec = load_strategy(SOURCE)
    base = validate_parameters(spec, {'record_indicators': False})
    return {variant_key(p): {'parameters': p} for values in product(*AXES.values())
            for p in [{**base, **dict(zip(AXES, values))}]}


def rank(results, period):
    return sorted(results, key=lambda k: (-results[k][period]['return_pct'], k))


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Frozen plan already exists; do not change it after seeing results')
    data = read(DOCS/'data.json')
    periods = {f'y{i+1}': [f'{2020+i}-09-10T00:00:00Z', f'{2021+i}-09-10T00:00:00Z'] for i in range(6)}
    periods.update(selection=['2020-09-10T00:00:00Z', '2024-09-10T00:00:00Z'],
                   recent=['2024-09-10T00:00:00Z', '2026-09-10T00:00:00Z'],
                   full=['2020-09-10T00:00:00Z', '2026-09-10T00:00:00Z'])
    variants = combinations()
    p = next(iter(variants.values()))['parameters']
    def reference(**changes):
        return variant_key({**p, 'center_length': 55, 'width_length': 31, 'trigger_mult': .8, 'chase_mult': 2.,
                            'activation_pct': 2., 'giveback_pct': 50., 'initial_stop_pct': 0., **changes})
    plan = dict(created_at=datetime.now(timezone.utc).isoformat(), symbol='ETH/USDT', timeframe='15m',
                start=data['start'], end=data['end'], warmup=650, initial_cash=10000, position_pct=100,
                data_gap_policy='observed_bars', data_hash=data['data_hash'], axes=AXES, variants=variants, periods=periods,
                original=reference(), previous_winner=reference(activation_pct=3.),
                requested_example=reference(center_length=65, width_length=40, activation_pct=3., giveback_pct=40.),
                requested_example_stop=reference(center_length=65, width_length=40, activation_pct=3., giveback_pct=40., initial_stop_pct=1.),
                selection_rule='Evaluate all 128 on first four years (2020-09 to 2024-09), rank return only, ID as tie break. Lock a single selection before evaluating remaining periods. No win-rate gate. Never substitute the six-year or recent-two-year leader for this frozen selection.',
                evaluation='Run the same 128 versions on each of six individual anniversary years, the continuous full six years, and continuous recent two years. Rank within the SAME period; do not compare raw cumulative returns of unequal durations. Each yearly run starts/ends flat; full runs keep positions across anniversaries.',
                execution='Unchanged single-file strategy v4 and engine v4; no fees, slippage, leverage, adding, fixed target. Signal at close, next observed open. Raw opposite exit independent of entry filter. Profit protection ratchets after close for next candle. Fixed initial stop uses actual entry open.',
                gaps=data['gaps'], gap_rule='No synthetic, interpolated or zero-volume candles. Existing engine sees strictly increasing observed timestamps. Across a gap it holds position/pending intent to next observed open; existing gap-stop behavior applies. Missing intragap price path remains unknown. Count affected trades; report removing their returns as an accounting sensitivity check, NOT another executable strategy or a selection score.',
                limit='Seven binary axes, every Cartesian combination: 128 versions x 9 periods = 1152 simulations. Stop after this fixed grid; no post-result expansion.',
                publication='Save config, source snapshot, data hash, and all nine trade/signal/equity traces for EACH version. Create formal chart records for union of top five full-six-year, frozen selection, top recent-two-year, original, previous winner and both requested examples. Reuse a matching verified record only for identical range/data/strategy/parameters; formal replays are verification, not research variants.',
                caveat='Parameter ranges were informed by earlier repeated examination of 2024-2026, which is not untouched out-of-sample. Earlier four years are new to this family study, but full-six-year selection is still retrospective. Two values per axis do not establish a global or long-term optimum; nominal repeated full-equity compounding ignores costs by user instruction.')
    assert len(variants) == 128 and all(plan[k] in variants for k in ['original', 'previous_winner', 'requested_example', 'requested_example_stop'])
    save(DOCS/'plan.json', plan)
    save(RUNTIME/'strategy-metadata.json', {'strategy_hash': digest(SOURCE.read_bytes()), 'engine_hash': digest((ROOT/'app/domain/local_backtest.py').read_bytes())})
    (RUNTIME/'strategy.py').write_bytes(SOURCE.read_bytes())
    for key, v in variants.items():
        save(RUNTIME/'variants'/f'{key}.json', {'strategy': SOURCE.stem, 'source_snapshot': str(RUNTIME/'strategy.py'),
            'data_hash': plan['data_hash'], 'data_gap_policy': plan['data_gap_policy'], 'periods': periods, **v})
    snapshot('026-frozen-six-year-combinations', [SOURCE, ROOT/'scripts/cloud_joint_study.py', ROOT/'test/test_cloud_joint_study.py',
        ROOT/'app/domain/backtest_history.py', ROOT/'app/contracts/local_backtest.py', ROOT/'scripts/local_backtest_worker.py',
        ROOT/'scripts/local_backtest_cli.py', ROOT/'test/test_backtest_history.py', DOCS/'plan.json', DOCS/'data.json', DOCS/'gap-recheck.json'])
    print('Frozen 128 combinations x 9 periods; six years; existing simulator; no costs', flush=True)


_state = None


def init_worker(plan, provenance):
    global _state
    raw = (RUNTIME/'data.json').read_bytes()
    assert digest(raw) == plan['data_hash']
    bars, gaps = validate_observed_bars(json.loads(raw), stamp(plan['start']), stamp(plan['end']), 900000, 650, stamp(plan['end']))
    assert gaps == plan['gaps']
    old = read(OLD/'results.json')
    references = {token(v['parameters']): k for k, v in old['variants'].items()}
    _state = (plan, provenance, bars, [b.timestamp for b in bars], references)


def gap_sensitivity(trades, gaps):
    affected = [t for t in trades if any(t['entry_time'] <= g['end'] and t['exit_time'] >= g['start'] for g in gaps)]
    ids = {t['trade_id'] for t in affected}
    return dict(affected_trades=len(affected), affected_trade_ids=sorted(ids),
                affected_wins=sum(t['profit'] > 0 for t in affected), affected_losses=sum(t['profit'] < 0 for t in affected),
                return_with_affected_set_to_zero_pct=(prod(1+t['return_pct']/100 for t in trades if t['trade_id'] not in ids)-1)*100,
                note='Accounting stress only. Does not recreate a tradable strategy; indicators after a gap can also be affected.')


def calculate(task):
    key, periods = task
    plan, provenance, bars, times, references = _state
    output = {}
    params = plan['variants'][key]['parameters']
    for period in periods:
        path = RUNTIME/f'{key}-{period}.json'
        if path.exists():
            trace = read(path)
            assert trace['provenance'] == provenance and trace['parameters'] == params
            output[period] = trace['metrics']
            continue
        start, end = plan['periods'][period]
        a, b = bisect_left(times, stamp(start)), bisect_left(times, stamp(end))
        assert a >= 650 and times[a] == stamp(start) and times[b-1]+900000 == stamp(end)
        module, spec = load_strategy(SOURCE)
        result = simulate(bars[a-650:b], module, validate_parameters(spec, params), warmup=650, step_ms=900000,
                          initial_cash=plan['initial_cash'], position_pct=plan['position_pct'])
        m = metrics(result)
        m.pop('daily_equity', None)
        m.pop('monthly_returns', None)
        m['gap_sensitivity'] = gap_sensitivity(result['trades'], [g for g in plan['gaps'] if g['start'] >= stamp(start) and g['end'] <= stamp(end)])
        reference = references.get(token(params))
        if reference and period in ('recent', 'y5'):
            old_period = 'full' if period == 'recent' else 'selection'
            old = read(ROOT/f'.heimdall_runtime/cloud-parameters-20260910/{reference}-{old_period}.json')
            assert all(result[k] == old[k] for k in ('report', 'trades', 'signals', 'equity'))
            m['old_record_exact'] = reference+'-'+old_period
        trace = {k: result[k] for k in ('report', 'trades', 'signals')}
        trace['equity'] = [{'timestamp': x['timestamp'], 'equity': x['equity']} for x in result['equity']]
        trace.update(metrics=m, provenance=provenance, parameters=params, period=[start, end])
        save(path, trace)
        output[period] = m
    return key, output


def interactions(plan, results, period):
    output = {}
    for field, (low, high) in plan['axes'].items():
        pairs = []
        for key, v in plan['variants'].items():
            p = v['parameters']
            if p[field] != low:
                continue
            other = variant_key({**p, field: high})
            a, b = results[key][period]['return_pct'], results[other][period]['return_pct']
            pairs.append({'from': key, 'to': other, 'return_change_pct_points': b-a})
        output[field] = dict(from_value=low, to_value=high, comparisons=len(pairs),
                             better=sum(p['return_change_pct_points'] > 1e-8 for p in pairs),
                             worse=sum(p['return_change_pct_points'] < -1e-8 for p in pairs),
                             median_change_pct_points=median(p['return_change_pct_points'] for p in pairs))
    return output


def study(workers):
    plan = read(DOCS/'plan.json')
    files = [SOURCE, ROOT/'scripts/cloud_joint_study.py', ROOT/'app/domain/local_backtest.py', ROOT/'app/domain/backtest_history.py',
             ROOT/'scripts/profit_protection_study.py', ROOT/'scripts/trend_cloud_study.py', ROOT/'app/services/local_backtest_strategies.py', DOCS/'plan.json']
    provenance = dict(files={f.relative_to(ROOT).as_posix(): digest(f.read_bytes()) for f in files}, environment=environment(), data_hash=plan['data_hash'])
    path = DOCS/'results.json'
    out = read(path) if path.exists() else dict(plan=plan, provenance=provenance, results={}, status='running')
    assert out['provenance'] == provenance
    with ProcessPoolExecutor(max_workers=workers, initializer=init_worker, initargs=(plan, provenance)) as pool:
        for stage, periods in [('selection', ['selection']), ('evaluation', [p for p in plan['periods'] if p != 'selection'])]:
            jobs = [pool.submit(calculate, (key, periods)) for key in plan['variants']]
            for i, job in enumerate(as_completed(jobs), 1):
                key, values = job.result()
                out['results'].setdefault(key, {}).update(values)
                save(path, out)
                chosen_period = 'selection' if stage == 'selection' else 'full'
                print(f'{stage} {i}/128 {key}: {values[chosen_period]["return_pct"]:+.2f}%', flush=True)
            if stage == 'selection':
                ranking = rank(out['results'], 'selection')
                selection = dict(provenance=provenance, ranking=ranking, selected=ranking[0])
                if (DOCS/'selection.json').exists():
                    assert read(DOCS/'selection.json') == selection
                else:
                    save(DOCS/'selection.json', selection)
                out['selection'] = selection
                save(path, out)
                print('LOCKED FIRST FOUR YEARS: '+ranking[0], flush=True)
    out['rankings'] = {p: rank(out['results'], p) for p in plan['periods']}
    out['interactions'] = {p: interactions(plan, out['results'], p) for p in ('full', 'recent', 'selection')}
    top = out['rankings']['full'][0]
    top_params = plan['variants'][top]['parameters']
    out['top_neighbors'] = [variant_key({**top_params, f: next(v for v in values if v != top_params[f])}) for f, values in plan['axes'].items()]
    out['chart_keys'] = list(dict.fromkeys(out['rankings']['full'][:5]+[out['selection']['selected'], out['rankings']['recent'][0],
                           plan['original'], plan['previous_winner'], plan['requested_example'], plan['requested_example_stop']]))
    out['simulations'] = sum(len(x) for x in out['results'].values())
    assert out['simulations'] == 1152
    out.update(status='completed', completed_at=datetime.now(timezone.utc).isoformat())
    save(path, out)
    print('Completed 1152. Full six-year leader: '+top, flush=True)


def publish():
    r = read(DOCS/'results.json')
    assert r['status'] == 'completed'
    path = DOCS/'project-runs.json'
    receipt = read(path) if path.exists() else dict(provenance=r['provenance'], runs={})
    assert receipt['provenance'] == r['provenance']
    d = build_database_runtime(settings)
    s = LocalBacktestService(d)
    try:
        for key in r['chart_keys']:
            if key not in receipt['runs']:
                cmd = {k: r['plan'][k] for k in ('symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct', 'data_gap_policy')}
                cmd.update(strategy=SOURCE.stem, parameters={**r['plan']['variants'][key]['parameters'], 'record_indicators': True})
                record = s.create(LocalBacktestCommand.model_validate(cmd))
                receipt['runs'][key] = dict(run_id=record['id'], verified=False)
                save(path, receipt)
            item = receipt['runs'][key]
            record = s.repository.get(item['run_id'])
            if record['status'] == 'completed' and not item['verified']:
                actual = read(s.directory(record['id'])/'result.json')
                expected = read(RUNTIME/f'{key}-full.json')
                assert record['metadata']['data_hash'] == r['provenance']['data_hash']
                assert record['metadata']['history_gaps'] == r['plan']['gaps']
                assert all(actual[k] == expected[k] for k in ('report', 'trades', 'signals'))
                assert [{'timestamp': p['timestamp'], 'equity': p['equity']} for p in actual['equity']] == expected['equity']
                item['verified'] = True
                save(path, receipt)
            print(key, record['status'], item['verified'], item['run_id'], flush=True)
    finally:
        d.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'publish'])
    parser.add_argument('--workers', type=int, default=2, choices=[1, 2])
    args = parser.parse_args()
    if args.action == 'run': study(args.workers)
    elif args.action == 'prepare': prepare()
    else: publish()
