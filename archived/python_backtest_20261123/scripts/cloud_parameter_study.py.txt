"""Frozen EMA55 factor study; cached project bars and the existing execution engine only."""
import argparse
from bisect import bisect_left
from datetime import datetime, timezone
import json

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import Bar, simulate
from app.domain.backtest_diagnostics import summarize
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import digest, environment, load_strategy, validate_parameters
from config import settings
from scripts.cloud_robustness_study import ROOT, stitched
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import read, save, metrics, paired_entries
from scripts.trend_cloud_study import stamp

DOCS = ROOT/'docs/verification/eth-cloud-parameters-20260910'
RUNTIME = ROOT/'.opentrading_runtime/cloud-parameters-20260910'
SOURCE = ROOT/'strategies/trend_cloud_parameters_v4.py'
BASELINE = ROOT/'.opentrading_runtime/local_backtests/4c549bfe4fe0496fa43830193dd06728'
GROUPS = {
    'center': ('中心线周期', ['center_length']),
    'width': ('振幅平均周期', ['width_length']),
    'trigger': ('突破门槛', ['trigger_mult']),
    'chase': ('最远入场距离', ['chase_mult']),
    'activation': ('利润保护启动点', ['activation_pct']),
    'giveback': ('允许利润回吐', ['giveback_pct']),
    'stop': ('初始止损', ['initial_stop_pct', 'initial_stop_width']),
}


def rank(rows):
    return sorted(rows, key=lambda key: (-rows[key]['return_pct'], key))


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Frozen plan exists; use a new version for changes')
    previous = read(ROOT/'docs/verification/eth-cloud-manual-20260910/plan.json')
    plan = {k: previous[k] for k in ('symbol', 'timeframe', 'start', 'end', 'warmup', 'data_hash', 'periods', 'initial_cash', 'position_pct')}
    _, spec = load_strategy(SOURCE)
    defaults = validate_parameters(spec, {'record_indicators': False})
    variants = {'baseline': dict(name='原第一名：EMA55／距离2W／保护2%与50%／无初始止损', group='baseline', parameters=defaults)}

    def add(key, name, group, **changes):
        variants[key] = dict(name=name, group=group, parameters={**defaults, **changes})

    for n in (21, 31, 45, 65, 89):
        add(f'center{n}', f'中心线 EMA{n}', 'center', center_length=n)
    for n in (14, 21, 40, 55):
        add(f'width{n}', f'振幅平均 EMA{n}', 'width', width_length=n)
    for m in (.4, .6, 1., 1.2):
        add(f'trigger{round(m*100)}', f'突破门槛 {m:g}W', 'trigger', trigger_mult=m)
    for m in (0, 1.25, 1.5, 2.5, 3.):
        add(f'chase{round(m*100)}', f'最多离中心 {m:g}W' if m else '不限制追价距离', 'chase', chase_mult=m)
    for a in (0, .5, 1., 1.5, 2.5, 3.):
        add(f'activate{round(a*100)}', f'浮盈 {a:g}% 启动保护' if a else '关闭利润保护，只按反向信号退出', 'activation', activation_pct=a)
    for g in (25, 40, 60, 75):
        add(f'giveback{g}', f'最高浮盈允许回吐 {g}%', 'giveback', giveback_pct=g)
    for s in (.5, 1., 1.5, 2., 3.):
        add(f'stop{round(s*100)}', f'入场后亏 {s:g}% 初始止损', 'stop', initial_stop_pct=s)
    for w in (2., 3., 4.):
        add(f'stopW{w:g}', f'初始止损按信号振幅 {w:g}W', 'stop', initial_stop_width=w)
    assert len(variants) == 37
    plan.update(created_at=datetime.now(timezone.utc).isoformat(), baseline_run=BASELINE.name, variants=variants,
        objective='Test the historical return leader EMA55: seven factors and two initial-stop sizing methods. Rank only by return; report win/loss and drawdown descriptively, with no eligibility gates.',
        selection='Run the first year for all 37 fixed single-factor versions. Within each factor include baseline, pick maximum first-year return; exact tie prefers baseline then ID. Lock the winners before any later-period run.',
        combinations={'entry_combo': ['center', 'width', 'trigger', 'chase'], 'exit_combo': ['activation', 'giveback', 'stop'], 'all_combo': list(GROUPS)},
        combination_rule='Construct exactly three combinations using only the locked first-year factor winners. Evaluate their first year, rank all 40 by first-year return and lock a single choice before later periods. Do not replace that choice with later/full winner. Duplicate parameter sets are retained and disclosed; no further search.',
        execution=[
            'Unchanged cached Binance spot ETH/USDT 15m data, engine v4, 650 warmup, no fees/slippage/leverage, 100% current equity. Single position, no additions.',
            'Center EMA(hl2,N); W=EMA(high-low,M), NOT ATR. Close crosses center +/- trigger*W; directional close-to-center distance <= chase*W. Zero chase means no distance restriction. Signal close only, fill next open; no extra next-open chase check.',
            'Entry filters do not suppress the raw opposite exit. Same-side entry signals cannot reset a live stop. No fixed take-profit.',
            'Initial percent stop uses actual fill. Width stop sets percent=100*multiple*signal_W/signal_close, then engine applies this percent to actual fill. Width frozen at decision, no future-volatility widening.',
            'Initial stop is active on the entry candle. Profit protection ratchets it in the profitable direction, never loosens it. Either initial/profit stop or raw opposite signal can exit.',
            'Peak favorable high/low is updated after each close; tightened protection applies next bar. Gaps through an active stop fill at actual open. The retained-profit percentage is not a guaranteed execution price.',
            'Four later quarters start/end flat and compound for the following-year report. Full two-year backtest is continuous. These two conventions need not have identical transactions at boundaries.'
        ],
        limit='37 single-factor configurations plus exactly 3 predeclared first-year-selected combinations, six periods each = 240 simulations. 40 full-period project records reproduce these, not new research trials. No expansion after results.',
        caveat='Both years already inspected repeatedly; chronological selection here checks transfer within reused history, not untouched out-of-sample. No claim that the best tested value is a long-term global optimum.')
    save(DOCS/'plan.json', plan)
    snapshot('022-frozen-ema55-parameters', [SOURCE, ROOT/'scripts/cloud_parameter_study.py', ROOT/'test/test_cloud_parameters.py', DOCS/'plan.json'])
    print('Frozen 37 single-factor versions + 3 first-year-selected combinations; 240 simulations', flush=True)


def factor_winners(variants, rows):
    return {g: min(['baseline']+[k for k, v in variants.items() if v['group'] == g],
                   key=lambda k: (-rows[k]['return_pct'], k != 'baseline', k)) for g in GROUPS}


def study():
    plan = read(DOCS/'plan.json')
    files = [SOURCE, ROOT/'scripts/cloud_parameter_study.py', ROOT/'scripts/cloud_robustness_study.py',
             ROOT/'scripts/profit_protection_study.py', ROOT/'scripts/trend_cloud_study.py',
             ROOT/'app/domain/local_backtest.py', ROOT/'app/domain/backtest_diagnostics.py', ROOT/'app/services/local_backtest_strategies.py', DOCS/'plan.json']
    provenance = dict(files={p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in files}, environment=environment())
    raw = (BASELINE/'data.json').read_bytes()
    assert digest(raw) == plan['data_hash']
    provenance['data_hash'] = digest(raw)
    bars = [Bar(int(r[0]), *map(float, r[1:])) for r in json.loads(raw)]
    times = [b.timestamp for b in bars]
    assert all(b-a == 900000 for a, b in zip(times, times[1:]))
    path = DOCS/'results.json'
    output = read(path) if path.exists() else dict(plan=plan, variants=dict(plan['variants']), provenance=provenance, results={}, status='running')
    assert output['provenance'] == provenance

    def calculate(key, period):
        trace_path = RUNTIME/f'{key}-{period}.json'
        if period in output['results'].get(key, {}):
            trace = read(trace_path)
            assert trace['provenance'] == provenance
            return trace
        start, end = plan['periods'][period]
        a, b = bisect_left(times, stamp(start)), bisect_left(times, stamp(end))
        assert a >= 650 and b-a == (stamp(end)-stamp(start))//900000
        module, spec = load_strategy(SOURCE)
        params = validate_parameters(spec, output['variants'][key]['parameters'])
        result = simulate(bars[a-650:b], module, params, warmup=650, step_ms=900000, initial_cash=10000, position_pct=100)
        if key == 'baseline':
            old_period = {'selection': 'q1-train', 'full': 'full'}.get(period, period+'-test')
            old = read(ROOT/f'.opentrading_runtime/cloud-robustness-20260910/center55-{old_period}.json')
            assert result['trades'] == old['trades'] and result['equity'] == old['equity'], 'Baseline changed'
            if period == 'full':
                formal = read(BASELINE/'result.json')
                assert result['report'] == formal['report'] and result['signals'] == formal['signals']
            output.setdefault('baseline_exact_periods', []).append(period)
        m = metrics(result)
        output['results'].setdefault(key, {})[period] = m
        trace = {k: result[k] for k in ('report', 'trades', 'signals', 'equity')}
        trace.update(provenance=provenance, parameters=params, period=[start, end])
        save(trace_path, trace)
        save(path, output)
        print(f'{period} {key}: {m["return_pct"]:+.2f}% | {m["wins"]} wins / {m["losses"]} losses', flush=True)
        return trace

    for key in plan['variants']:
        calculate(key, 'selection')
    chosen = factor_winners(plan['variants'], {k: output['results'][k]['selection'] for k in plan['variants']})
    lock = dict(provenance=provenance, chosen=chosen, combinations={})
    for key, groups in plan['combinations'].items():
        p = dict(plan['variants']['baseline']['parameters'])
        for group in groups:
            for field in GROUPS[group][1]:
                p[field] = plan['variants'][chosen[group]]['parameters'][field]
        name = {'entry_combo': '前一年挑出的入场参数组合', 'exit_combo': '前一年挑出的退出参数组合', 'all_combo': '前一年挑出的入场＋退出组合'}[key]
        lock['combinations'][key] = dict(name=name, group='combined', parameters=p)
    lock_path = DOCS/'factor-selection.json'
    if lock_path.exists():
        assert read(lock_path) == lock
    else:
        save(lock_path, lock)
    output['variants'].update(lock['combinations'])
    output['factor_selection'] = lock
    for key in lock['combinations']:
        calculate(key, 'selection')
    ranking = rank({k: output['results'][k]['selection'] for k in output['variants']})
    choice = dict(provenance=provenance, ranking=ranking, selected=ranking[0])
    if (DOCS/'selection.json').exists():
        assert read(DOCS/'selection.json') == choice
    else:
        save(DOCS/'selection.json', choice)
    output['selection'] = choice
    save(path, output)
    print('LOCKED FIRST-YEAR CHOICE: '+choice['selected'], flush=True)
    output['following_year'] = {}
    for key in output['variants']:
        joined = stitched([(f'q{i}', calculate(key, f'q{i}')) for i in range(1, 5)])
        summary = summarize(joined['trades'], include_streak=True)
        output['following_year'][key] = {**joined['report'], **summary,
            'average_win_return_pct': summary['avg_win_return_pct'],
            'average_loss_return_pct': summary['avg_loss_return_pct']}
        save(RUNTIME/f'{key}-following-year.json', joined)
        calculate(key, 'full')
    output['rankings'] = {p: rank({k: output['results'][k][p] for k in output['variants']}) for p in plan['periods']}
    output['rankings']['following_year'] = rank(output['following_year'])
    output['paired_stops'] = {}
    for period in ('selection', 'full'):
        base = read(RUNTIME/f'baseline-{period}.json')
        output['paired_stops'][period] = {k: paired_entries(base, read(RUNTIME/f'{k}-{period}.json'))
                                          for k, v in output['variants'].items() if v['group'] == 'stop'}
    output['simulations'] = sum(len(v) for v in output['results'].values())
    assert output['simulations'] == 240 and len(output['baseline_exact_periods']) == 6
    output['status'] = 'completed'
    output['completed_at'] = datetime.now(timezone.utc).isoformat()
    save(path, output)
    print('Completed 240 simulations. Full-period leader: '+output['rankings']['full'][0], flush=True)


def publish():
    data = read(DOCS/'results.json')
    assert data['status'] == 'completed'
    assert data['provenance']['files'][SOURCE.relative_to(ROOT).as_posix()] == digest(SOURCE.read_bytes())
    receipt_path = DOCS/'project-runs.json'
    receipt = read(receipt_path) if receipt_path.exists() else dict(provenance=data['provenance'], runs={})
    assert receipt['provenance'] == data['provenance']
    database = build_database_runtime(settings)
    service = LocalBacktestService(database)
    try:
        for key, v in data['variants'].items():
            if key not in receipt['runs']:
                cmd = {k: data['plan'][k] for k in ('symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct')}
                cmd.update(strategy=SOURCE.stem, parameters={**v['parameters'], 'record_indicators': True})
                record = service.create(LocalBacktestCommand.model_validate(cmd))
                receipt['runs'][key] = dict(run_id=record['id'], verified=False)
                save(receipt_path, receipt)
            record = service.repository.get(receipt['runs'][key]['run_id'])
            if record['status'] == 'completed' and not receipt['runs'][key]['verified']:
                actual = read(service.directory(record['id'])/'result.json')
                expected = read(RUNTIME/f'{key}-full.json')
                assert record['metadata']['data_hash'] == data['provenance']['data_hash']
                assert all(actual[k] == expected[k] for k in ('report', 'trades', 'signals', 'equity'))
                receipt['runs'][key]['verified'] = True
                save(receipt_path, receipt)
            print(f'{key}: {record["status"]}, verified={receipt["runs"][key]["verified"]}, {record["id"]}', flush=True)
    finally:
        database.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'publish'])
    args = parser.parse_args()
    {'prepare': prepare, 'run': study, 'publish': publish}[args.action]()
