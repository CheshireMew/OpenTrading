"""Run the fixed ETH comparison through OpenTrading services and saved snapshots.

prepare queues normal, user-visible backtests. analyze reads completed runs and
uses the same public simulator for historical subperiods. No data downloader.
"""
import argparse
from bisect import bisect_left
from datetime import datetime, timezone
import json
from pathlib import Path

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import Bar, simulate
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import digest, load_strategy, validate_parameters
from config import settings


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'docs/verification/eth-cloud-two-year-20260910'
RUNTIME = ROOT/'.opentrading_runtime/eth-cloud-two-year-20260910'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def stamp(iso):
    return int(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()*1000)


def describe(result):
    report = dict(result['report'])
    report['return_to_drawdown'] = report['return_pct']/report['max_drawdown_pct'] if report['max_drawdown_pct'] else None
    for side in ('long', 'short'):
        trades = [t for t in result['trades'] if t['side'] == side]
        report[side] = {'trades': len(trades), 'profit': sum(t['profit'] for t in trades),
                        'wins': sum(t['profit'] > 0 for t in trades)}
    initial = result['equity'][0]['equity']
    monthly, daily = {}, {}
    for point in result['equity'][1:]:
        dt = datetime.fromtimestamp((point['timestamp']-1)/1000, timezone.utc)
        monthly[dt.strftime('%Y-%m')] = point['equity']
        daily[dt.strftime('%Y-%m-%d')] = point['equity']
    previous, months = initial, []
    for month, equity in monthly.items():
        months.append({'month': month, 'return_pct': (equity/previous-1)*100 if previous > 0 else None})
        previous = equity
    report['monthly_returns'] = months
    report['positive_months'] = sum(m['return_pct'] is not None and m['return_pct'] > 0 for m in months)
    report['month_count'] = len(months)
    report['daily_equity'] = [{'date': date, 'equity': value} for date, value in daily.items()]
    return report


def prepare(service, plan, receipt_path, reuse):
    plan_hash = digest((DIRECTORY/'plan.json').read_bytes())
    receipt = read(receipt_path) if receipt_path.exists() else {'plan_hash': plan_hash, 'runs': {}}
    if receipt['plan_hash'] != plan_hash:
        raise ValueError('计划已变化，请先核对现有运行，不能混用')
    for variant in plan['variants']:
        if variant in receipt['runs']:
            continue
        command = {key: plan[key] for key in ('symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct')}
        command.update(strategy='trend_cloud_comparison', parameters={'variant': variant, 'record_indicators': True, 'long_only': False})
        if variant == 'ema31_atr' and reuse:
            run = service.repository.get(reuse)
            expected = LocalBacktestCommand.model_validate(command).model_dump(mode='json')
            if run['config'] != expected or run['archived']:
                raise ValueError('指定复用运行与无成本计划不一致')
        else:
            run = service.create(LocalBacktestCommand.model_validate(command))
        receipt['runs'][variant] = run['id']
        save(receipt_path, receipt)
        print(f"Queued {variant}: {run['id']}", flush=True)
    return receipt


def analyze(service, plan, receipt):
    if digest((DIRECTORY/'plan.json').read_bytes()) != receipt['plan_hash']:
        raise ValueError('分析计划与已保存的运行计划不同')
    runs = {v: service.repository.get(i) for v, i in receipt['runs'].items()}
    incomplete = {v: {'id': r['id'], 'status': r['status'], 'progress': r['progress'], 'error': r.get('error')}
                  for v, r in runs.items() if r['status'] != 'completed'}
    if incomplete or set(runs) != set(plan['variants']):
        print(json.dumps({'incomplete': incomplete, 'completed': len(runs)-len(incomplete)}, ensure_ascii=False))
        return False
    first = runs['ema31_atr']
    folder = service.directory(first['id'])
    raw = (folder/'data.json').read_bytes()
    if digest(raw) != first['metadata']['data_hash']:
        raise ValueError('正式行情快照校验失败')
    for run in runs.values():
        if run['metadata']['data_hash'] != digest(raw) or run['metadata']['strategy_hash'] != first['metadata']['strategy_hash']:
            raise ValueError('比较运行的行情或源码不同')
        if any(run['config'].get(k, 0) for k in ('fee_pct', 'slippage_pct')):
            raise ValueError('禁止把成本试算混入本研究')
    bars = [Bar(int(row[0]), *map(float, row[1:])) for row in json.loads(raw)]
    times = [b.timestamp for b in bars]
    output = {'plan': plan, 'plan_hash': receipt['plan_hash'], 'data_hash': digest(raw),
              'strategy_hash': first['metadata']['strategy_hash'], 'source': first['metadata']['source'],
              'main_bars': len(bars)-plan['warmup_bars'], 'results': {}}

    # First-year selection is completed and persisted before reading the
    # validation-period performance of any candidate.
    selection = {}
    for variant in plan['variants']:
        source = service.directory(runs[variant]['id'])/'strategy.py'
        pstart, pend = map(stamp, plan['periods']['selection'])
        a, b = bisect_left(times, pstart), bisect_left(times, pend)
        module, spec = load_strategy(source)
        p = validate_parameters(spec, {'variant': variant, 'record_indicators': False, 'long_only': False})
        result = simulate(bars[a-spec.warmup_bars:b], module, p, warmup=spec.warmup_bars, step_ms=900000,
                          initial_cash=plan['initial_cash'], position_pct=plan['position_pct'])
        selection[variant] = describe(result)
    eligible = [v for v, r in selection.items() if v not in ('cash', 'buy_hold') and r['return_pct'] > 0
                and r['profit_factor'] is not None and r['profit_factor'] > 1 and r['total_trades'] >= 30]
    eligible.sort(key=lambda v: (selection[v]['return_to_drawdown'] or 0, selection[v]['return_pct']), reverse=True)
    output['selection_ranking'] = eligible
    output['selection_winner'] = eligible[0] if eligible else None
    save(DIRECTORY/'selection.json', {'plan_hash': receipt['plan_hash'], 'ranking': eligible, 'results': selection})
    print('Selection locked: '+str(output['selection_winner']), flush=True)

    signal_sets = {}
    for variant, name in plan['variants'].items():
        run = runs[variant]
        run_folder = service.directory(run['id'])
        full = read(run_folder/'result.json')
        signal_sets[variant] = {(s['timestamp'], s['action']) for s in full['signals']}
        if abs(full['report']['final_equity']-full['equity'][-1]['equity']) > 1e-6:
            raise ValueError('期末权益与曲线不一致')
        if abs(full['report']['profit']-sum(t['profit'] for t in full['trades'])) > 1e-6:
            raise ValueError('逐笔利润与报告不一致')
        item = {'name': name, 'run_id': run['id'], 'full': describe(full), 'selection': selection[variant]}
        for period in ('validation', 'recent', 'long_only'):
            pstart, pend = map(stamp, plan['periods'][period] if period in plan['periods'] else [plan['start'], plan['end']])
            a, b = bisect_left(times, pstart), bisect_left(times, pend)
            module, spec = load_strategy(run_folder/'strategy.py')
            p = validate_parameters(spec, {'variant': variant, 'record_indicators': False, 'long_only': period == 'long_only'})
            result = simulate(bars[a-spec.warmup_bars:b], module, p, warmup=spec.warmup_bars, step_ms=900000,
                              initial_cash=plan['initial_cash'], position_pct=plan['position_pct'])
            item[period] = describe(result)
            # Keep the trace, not only selected statistics, for reproducibility.
            save(RUNTIME/f'{variant}-{period}.json', {**result, 'period': [pstart, pend], 'parameters': p,
                                                     'source_run_id': run['id'], 'data_hash': digest(raw)})
        output['results'][variant] = item
        save(DIRECTORY/'results.json', output)
        print(f"Analyzed {variant}: full {item['full']['return_pct']:.2f}%, validation {item['validation']['return_pct']:.2f}%", flush=True)
    output['full_return_ranking'] = sorted([v for v in runs if v not in ('cash', 'buy_hold')],
                                          key=lambda v: output['results'][v]['full']['return_pct'], reverse=True)
    baseline = signal_sets['ema31_atr']
    output['signal_comparison_to_ema31_atr'] = {
        variant: {'reference_signals': len(baseline), 'candidate_signals': len(events), 'shared': len(events & baseline),
                  'missing': len(baseline-events), 'extra': len(events-baseline),
                  'jaccard': len(events & baseline)/len(events | baseline) if events | baseline else None}
        for variant, events in signal_sets.items()}
    save(DIRECTORY/'results.json', output)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'status', 'analyze'])
    parser.add_argument('--reuse')
    args = parser.parse_args()
    plan = read(DIRECTORY/'plan.json')
    receipt_path = DIRECTORY/'runs.json'
    database = build_database_runtime(settings)
    service = LocalBacktestService(database)
    try:
        if args.action == 'prepare':
            prepare(service, plan, receipt_path, args.reuse)
        elif args.action == 'status':
            receipt = read(receipt_path)
            states = [service.repository.get(i) for i in receipt['runs'].values()]
            print(json.dumps([{'variant': s['config']['parameters']['variant'], 'id': s['id'], 'status': s['status'],
                               'progress': s['progress'], 'error': s.get('error')} for s in states], ensure_ascii=False, indent=2))
        elif not analyze(service, plan, read(receipt_path)):
            return 2
    finally:
        database.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
