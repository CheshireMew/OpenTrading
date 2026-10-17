"""Bounded width and profit-protection study using Heimdall snapshots/simulator."""
import argparse
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import Bar, ENGINE_VERSION, Intent, ProfitProtection, simulate
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import digest, environment, load_strategy, validate_parameters
from config import settings
from scripts.trend_cloud_study import describe, stamp

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'docs/verification/eth-profit-protection-20260910'
RUNTIME = ROOT/'.heimdall_runtime/profit-protection-study-20260910'
SOURCE = ROOT/'strategies/trend_cloud_profit_protection.py'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n', encoding='utf-8')


def key_for(n, mult, activation=0, giveback=40):
    return f'w{n}_m{round(mult*100)}'+(f'_a{activation}_g{giveback}' if activation else '')


def metrics(result):
    r = describe(result)
    trades = result['trades']
    wins, losses = ([t for t in trades if t['profit'] > 0], [t for t in trades if t['profit'] < 0])
    for label, group in (('win', wins), ('loss', losses)):
        r[f'average_{label}_amount'] = mean(abs(t['profit']) for t in group) if group else None
        r[f'average_{label}_return_pct'] = mean(abs(t['return_pct']) for t in group) if group else None
    r['exit_reasons'] = {reason: {'count': len(group), 'wins': sum(t['profit'] > 0 for t in group),
                                 'losses': sum(t['profit'] < 0 for t in group), 'profit': sum(t['profit'] for t in group)}
                         for reason in sorted({t['exit_reason'] for t in trades})
                         for group in [[t for t in trades if t['exit_reason'] == reason]]}
    r['signal_status'] = dict(Counter(s['status'] for s in result['signals']))
    streak = longest = 0
    for t in trades:
        streak = streak+1 if t['profit'] < 0 else 0
        longest = max(streak, longest)
    r['max_consecutive_losses'] = longest
    return r


def paired_entries(original, changed):
    one = {(t['entry_time'], t['side']): t for t in original['trades']}
    two = {(t['entry_time'], t['side']): t for t in changed['trades']}
    pairs = [(t, two[k]) for k, t in one.items() if k in two]
    original_losses = [(a, b) for a, b in pairs if a['profit'] < 0]
    original_wins = [(a, b) for a, b in pairs if a['profit'] > 0]
    return {
        'matched': len(pairs), 'baseline_trades': len(one), 'protected_trades': len(two),
        'baseline_unmatched_entries': len(one.keys()-two.keys()), 'additional_entries': len(two.keys()-one.keys()),
        'matched_baseline_losses': len(original_losses),
        'losses_turned_into_wins': sum(b['profit'] > 0 for a, b in original_losses),
        'losses_reduced': sum(b['return_pct'] > a['return_pct']+1e-10 for a, b in original_losses),
        'matched_baseline_winners': len(original_wins),
        'winners_reduced': sum(b['return_pct'] < a['return_pct']-1e-10 for a, b in original_wins),
        'winners_improved': sum(b['return_pct'] > a['return_pct']+1e-10 for a, b in original_wins),
        'winners_baseline_average_return_pct': mean(a['return_pct'] for a, b in original_wins) if original_wins else None,
        'winners_protected_average_return_pct': mean(b['return_pct'] for a, b in original_wins) if original_wins else None,
        'matched_average_return_change_pct_points': mean(b['return_pct']-a['return_pct'] for a, b in pairs) if pairs else None,
        'note': 'Matches by exact entry time and direction; compare percentage returns, since compounded principal changes. Additional re-entries are not included in the matched subset, but are included in complete performance.',
    }


def study():
    plan = read(DOCS/'plan.json')
    original_dir = ROOT/'.heimdall_runtime/local_backtests'/plan['baseline_run']
    raw = (original_dir/'data.json').read_bytes()
    if digest(raw) != plan['data_hash']:
        raise ValueError('Source snapshot differs from frozen plan')
    bars = [Bar(int(r[0]), *map(float, r[1:])) for r in json.loads(raw)]
    times = [b.timestamp for b in bars]
    provenance = {'plan_hash': digest((DOCS/'plan.json').read_bytes()), 'data_hash': digest(raw),
                  'strategy_hash': digest(SOURCE.read_bytes()),
                  'engine_hash': digest((ROOT/'app/domain/local_backtest.py').read_bytes()), 'environment': environment()}
    checkpoint = DOCS/'results.json'
    if checkpoint.exists():
        output = read(checkpoint)
        if output['provenance'] != provenance:
            raise ValueError('Study inputs changed; do not mix results')
    else:
        output = {'plan': plan, 'provenance': provenance, 'created_at': datetime.now(timezone.utc).isoformat(),
                  'variants': {}, 'results': {}, 'selection': {}, 'status': 'running'}
        (RUNTIME/'strategy.py').write_bytes(SOURCE.read_bytes())
        (RUNTIME/'engine.py').write_bytes((ROOT/'app/domain/local_backtest.py').read_bytes())
        save(checkpoint, output)

    def add(n, mult, activation=0, giveback=40, group='width'):
        key = key_for(n, mult, activation, giveback)
        output['variants'].setdefault(key, {'name': f'宽度EMA{n}／门槛{mult:g}'+(f'／盈利{activation}%启动／回吐{giveback}%' if activation else '／无利润保护'),
                                             'group': group, 'parameters': {'width_length': n, 'trigger_mult': mult,
                                             'activation_pct': activation, 'giveback_pct': giveback, 'record_indicators': False}})
        return key

    def run(key, period):
        if period in output['results'].get(key, {}):
            return output['results'][key][period]
        start, end = map(stamp, plan['periods'][period])
        a, b = bisect_left(times, start), bisect_left(times, end)
        module, spec = load_strategy(RUNTIME/'strategy.py')
        params = validate_parameters(spec, output['variants'][key]['parameters'])
        result = simulate(bars[a-650:b], module, params, warmup=650, step_ms=900000,
                          initial_cash=plan['initial_cash'], position_pct=plan['position_pct'])
        if key == key_for(31, .99) and period == 'full':
            old = read(original_dir/'result.json')
            assert result['trades'] == old['trades'], 'Disabled protection changed baseline trades'
            assert result['equity'] == old['equity'], 'Disabled protection changed baseline equity'
            output['baseline_exact_trades_equity'] = True
        report = metrics(result)
        output['results'].setdefault(key, {})[period] = report
        save(RUNTIME/f'{key}-{period}.json', {'parameters': params, 'period': [start, end], 'provenance': provenance,
                                           'report': result['report'], 'trades': result['trades'], 'signals': result['signals']})
        save(checkpoint, output)
        print(f"{period} {key}: {report['return_pct']:.2f}%, DD {report['max_drawdown_pct']:.2f}%, {report['total_trades']} trades", flush=True)
        return report

    def choose(keys):
        eligible = [k for k in keys if output['results'][k]['selection']['return_pct'] > 0 and
                    (output['results'][k]['selection']['profit_factor'] or 0) > 1 and
                    output['results'][k]['selection']['total_trades'] >= 50]
        eligible.sort(key=lambda k: (output['results'][k]['selection']['return_to_drawdown'],
                                    output['results'][k]['selection']['return_pct']), reverse=True)
        return eligible

    baseline_key = key_for(31, .99)
    widths = [add(n, m) for n in plan['width_lengths'] for m in plan['trigger_multipliers']]
    protections = [add(31, .99, a, g, 'protection') for a in plan['activation_percentages'] for g in plan['giveback_percentages']]
    for key in widths+protections:
        run(key, 'selection')
    width_rank = choose(widths)
    width_winner = width_rank[0] if width_rank else baseline_key
    output['selection']['width_ranking'] = width_rank
    output['selection']['width_choice'] = width_winner
    save(DOCS/'width-selection.json', {'provenance': provenance, 'selection': output['selection'],
                                     'results': {k: output['results'][k]['selection'] for k in widths+protections}})
    wp = output['variants'][width_winner]['parameters']
    combos = [add(wp['width_length'], wp['trigger_mult'], a, g, 'combination')
              for a in plan['activation_percentages'] for g in plan['giveback_percentages']]
    for key in combos:
        run(key, 'selection')
    baseline_protection_rank = choose([baseline_key]+protections)
    combined_rank = choose([width_winner]+combos)
    output['selection'].update(baseline_protection_ranking=baseline_protection_rank,
                               baseline_protection_choice=baseline_protection_rank[0] if baseline_protection_rank else baseline_key,
                               combined_ranking=combined_rank,
                               combined_choice=combined_rank[0] if combined_rank else width_winner)
    save(DOCS/'selection.json', {'provenance': provenance, 'selection': output['selection'],
                               'results': {k: r['selection'] for k, r in output['results'].items()}})
    print('SELECTION LOCKED: '+json.dumps(output['selection'], ensure_ascii=False), flush=True)
    for period in ('validation', 'recent', 'full'):
        for key in output['variants']:
            run(key, period)

    comparisons = {}
    for key, variant in output['variants'].items():
        p = variant['parameters']
        if not p['activation_pct']:
            continue
        base = key_for(p['width_length'], p['trigger_mult'])
        comparisons[key] = {}
        for period in ('selection', 'validation', 'recent', 'full'):
            old, new = read(RUNTIME/f'{base}-{period}.json'), read(RUNTIME/f'{key}-{period}.json')
            comparisons[key][period] = paired_entries(old, new)
        # Freeze baseline entries, eliminating extra re-entry timing changes.
        old = read(RUNTIME/f'{base}-full.json')
        schedule = {t['exit_time']-900000: 'close' for t in old['trades'] if t['exit_phase'] == 'open'}
        schedule.update({t['entry_time']-900000: t['side'] for t in old['trades']})
        protection = ProfitProtection(p['activation_pct'], p['giveback_pct'])
        strategy = SimpleNamespace(on_bar=lambda c: Intent(schedule[c.history[-1].timestamp],
                                    profit_protection=protection, reason='固定基准入场时刻，单独检查利润保护')
                                    if c.history[-1].timestamp in schedule else None)
        fixed = simulate(bars, strategy, {}, warmup=650, step_ms=900000, initial_cash=10000, position_pct=100)
        compare = paired_entries(old, fixed)
        assert compare['matched'] == len(old['trades']) and compare['additional_entries'] == 0
        comparisons[key]['fixed_baseline_entries_full'] = {'comparison': compare, 'report': metrics(fixed)}
        save(RUNTIME/f'{key}-fixed-entries-full.json', {'provenance': provenance, 'parameters': p,
                                                     'report': fixed['report'], 'trades': fixed['trades'], 'signals': fixed['signals']})
    output['entry_comparisons'] = comparisons
    output['status'] = 'completed'
    save(checkpoint, output)
    print(f"Completed {len(output['variants'])} variants, {4*len(output['variants'])} period simulations; disabled protection preserves baseline trades/equity.", flush=True)


def publish():
    output = read(DOCS/'results.json')
    assert output['status'] == 'completed'
    assert digest(SOURCE.read_bytes()) == output['provenance']['strategy_hash']
    receipt_path = DOCS/'project-runs.json'
    receipt = read(receipt_path) if receipt_path.exists() else {'provenance': output['provenance'], 'runs': {}}
    if receipt['provenance'] != output['provenance']:
        raise ValueError('Project receipt differs from study provenance')
    selection = output['selection']
    # Keep a visible example of protection even if the ranking favors no protection.
    protected = next((k for k in selection['baseline_protection_ranking'] if output['variants'][k]['parameters']['activation_pct']), None)
    keys = list(dict.fromkeys(k for k in [key_for(31, .99), selection['width_choice'],
                                         selection['baseline_protection_choice'], selection['combined_choice'], protected,
                                         key_for(31, .8, 2, 50)] if k in output['variants']))
    database = build_database_runtime(settings)
    service = LocalBacktestService(database)
    try:
        for key in keys:
            if key not in receipt['runs']:
                plan = output['plan']
                cmd = {k: plan[k] for k in ('symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct')}
                cmd.update(strategy='trend_cloud_profit_protection', parameters={**output['variants'][key]['parameters'], 'record_indicators': True})
                run = service.create(LocalBacktestCommand.model_validate(cmd))
                receipt['runs'][key] = {'run_id': run['id'], 'verified': False}
                save(receipt_path, receipt)
            run = service.repository.get(receipt['runs'][key]['run_id'])
            if run['status'] == 'completed':
                actual = read(service.directory(run['id'])/'result.json')
                expected = read(RUNTIME/f'{key}-full.json')
                assert run['metadata']['data_hash'] == output['provenance']['data_hash']
                assert run['metadata']['strategy_hash'] == output['provenance']['strategy_hash']
                assert actual['trades'] == expected['trades'] and actual['signals'] == expected['signals']
                assert actual['report'] == expected['report']
                receipt['runs'][key]['verified'] = True
                save(receipt_path, receipt)
            print(json.dumps({'key': key, 'id': run['id'], 'status': run['status'], 'progress': run['progress'], 'error': run.get('error')}), flush=True)
    finally:
        database.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'publish'])
    args = parser.parse_args()
    study() if args.action == 'run' else publish()
