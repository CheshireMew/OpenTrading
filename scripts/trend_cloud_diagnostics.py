"""Diagnose existing OpenTrading runs without downloading or changing execution."""
import argparse
from bisect import bisect_left
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median

from app.domain.backtest_diagnostics import diagnose
from app.domain.local_backtest import Bar, simulate
from app.contracts.local_backtest import LocalBacktestCommand
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import digest, load_strategy, validate_parameters
from config import settings
from scripts.trend_cloud_study import describe, stamp

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'docs/verification/eth-cloud-two-year-20260910'
RUNTIME = ROOT/'.opentrading_runtime/eth-cloud-two-year-20260910'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def baseline_diagnostics():
    runs = read(DOCS/'runs.json')['runs']
    output = {}
    for variant in ('high_low_ema', 'ema31_atr'):
        directory = ROOT/'.opentrading_runtime/local_backtests'/runs[variant]
        raw = (directory/'data.json').read_bytes()
        assert digest(raw) == read(directory/'metadata.json')['data_hash']
        bars = [Bar(int(r[0]), *map(float, r[1:])) for r in json.loads(raw)]
        output[variant] = {'run_id': runs[variant], 'data_hash': digest(raw)}
        for period in ('full', 'selection', 'validation', 'recent'):
            source = (directory/'result.json' if period == 'full' else
                      RUNTIME/f'experiment-{variant}-{period}.json' if period == 'selection' else
                      RUNTIME/f'{variant}-{period}.json')
            result = read(source)
            details = diagnose(bars, result, source='hl2' if variant == 'high_low_ema' else 'hlc3',
                               width_period=16 if variant == 'high_low_ema' else 14,
                               range_ema=variant == 'high_low_ema')
            assert abs(details['report']['profit']-result['report']['profit']) < 1e-6
            output[variant][period] = details['report']
            save(RUNTIME/f'{variant}-{period}-diagnostics.json', details)
    save(DOCS/'diagnostics.json', output)
    print('Saved baseline diagnosis and annotated trades.', flush=True)


def experiment_plan():
    path = DOCS/'experiments-plan.json'
    if path.exists():
        return read(path)
    old_plan = read(DOCS/'plan.json')
    plan = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'ETH/USDT 15m, existing two-year project snapshot, no fees or slippage',
        'inference_limit': 'Exploratory follow-up on already inspected history. First-year selection is frozen before new later-period outcomes, but neither the later period nor recent 18 days are untouched data.',
        'periods': {'selection': old_plan['periods']['selection'], 'validation': old_plan['periods']['validation'],
                    'recent': old_plan['periods']['recent'], 'full': [old_plan['start'], old_plan['end']]},
        'selection_rule': 'Within each original baseline, eligible changes must beat first-year baseline return, not increase maximum drawdown, have at least 50 trades and profit factor > 1. Rank eligible changes by return / drawdown; no later reselection.',
        'ablation': {
            'ema31_atr': {'name': '原候选：EMA31 hlc3＋ATR14', 'parameters': {'source': 'hlc3', 'width': 'atr', 'width_period': 14}},
            'ema31_range': {'name': '只将 ATR14 换成平滑高低差14', 'parameters': {'source': 'hlc3', 'width': 'range', 'width_period': 14}},
            'ema31_cross': {'name': '只去掉宽度，穿越中心线即换仓', 'parameters': {'source': 'hlc3', 'width': 'none', 'width_period': 14}},
            'fixed_band': {'name': '宽度固定为首年波动比例的中位数', 'parameters': {'source': 'hlc3', 'width': 'fixed', 'width_period': 14}},
            'hlc3_atr16': {'name': '只将 ATR14 改为 ATR16', 'parameters': {'source': 'hlc3', 'width': 'atr', 'width_period': 16}},
            'hl2_atr14': {'name': '只将中心价格 hlc3 改为 hl2', 'parameters': {'source': 'hl2', 'width': 'atr', 'width_period': 14}},
            'hl2_atr16': {'name': 'EMA31 hl2＋ATR16', 'parameters': {'source': 'hl2', 'width': 'atr', 'width_period': 16}},
            'high_low_ema': {'name': '高低价 EMA31 通道', 'parameters': {'source': 'hl2', 'width': 'range_ema', 'width_period': 16}},
        },
        'changes': {
            'distance2': {'name': '离中心线超过两倍宽度时不追单', 'parameters': {'entry_filter': 'distance2'}},
            'slope8': {'name': '中心线近两小时也向同方向走才入场', 'parameters': {'entry_filter': 'slope8'}},
            'efficiency25': {'name': '近五小时方向较一致才入场', 'parameters': {'entry_filter': 'efficiency25'}},
            'confirm2': {'name': '突破后下一根仍在门槛外才确认', 'parameters': {'confirmation': 2}},
            'stop2': {'name': '增加约两倍 ATR 的固定止损', 'parameters': {'stop_atr': 2}},
            'stop3': {'name': '增加约三倍 ATR 的固定止损', 'parameters': {'stop_atr': 3}},
            'target4': {'name': '增加约四倍 ATR 的固定止盈', 'parameters': {'target_atr': 4}},
            'stop2_target4': {'name': '约两倍 ATR 止损、四倍 ATR 止盈', 'parameters': {'stop_atr': 2, 'target_atr': 4}},
            'trail3': {'name': '增加约三倍 ATR 距离的跟随止损', 'parameters': {'trail_atr': 3}},
        },
        'execution_details': [
            'All centers EMA31, signal width coefficient 0.99. Only the listed factor changes.',
            'Entry filters cannot block an opposite signal closing the held side; a denied new entry leaves the account flat. No delayed entry unless a new crossing occurs.',
            'Two-close confirmation applies to both exits and entries. Second close must still be outside its current corresponding band; next open execution.',
            'Stop/target/trail percent = multiplier * signal-close ATR / signal close * 100. The simulator anchors this at actual next-open entry, so absolute distance approximates signal ATR if the open gaps.',
            'ATR for new exits is 14 on the old ATR candidate and 16 on the high-low candidate. No changing ATR distance after entry.',
            'Trail is active from entry, moves using completed candle extrema and becomes effective next candle. If stop and target both hit within one candle, stop wins and the ambiguity is counted.',
            'The fixed-width percentage uses only first-year median ATR14 / center, no outcome optimization. All other coefficients are fixed here; no parameter grid or retuning.',
        ],
    }
    save(path, plan)
    return plan


def experiments():
    plan = experiment_plan()
    runs = read(DOCS/'runs.json')['runs']
    directory = ROOT/'.opentrading_runtime/local_backtests'/runs['ema31_atr']
    raw = (directory/'data.json').read_bytes()
    source = ROOT/'strategies/trend_cloud_experiments.py'
    data_hash = digest(raw)
    assert data_hash == read(directory/'metadata.json')['data_hash']
    bars = [Bar(int(r[0]), *map(float, r[1:])) for r in json.loads(raw)]
    times = [b.timestamp for b in bars]
    start, end = map(stamp, plan['periods']['selection'])
    old, spec = load_strategy(directory/'strategy.py')
    calc = old.Calculation(validate_parameters(spec, {'variant': 'ema31_atr', 'record_indicators': True}))
    width_ratios = []
    for b in bars:
        if b.timestamp >= end:
            break
        observation = calc.update(b)
        if b.timestamp >= start:
            width_ratios.append(100*observation.values['宽度基准']/observation.values['中心线'])
    fixed_pct = median(width_ratios)
    variants = {k: {**v, 'group': 'ablation'} for k, v in plan['ablation'].items()}
    for base in ('high_low_ema', 'ema31_atr'):
        for change, v in plan['changes'].items():
            variants[base+'__'+change] = {'name': v['name'], 'baseline': base, 'group': 'improvement',
                                         'parameters': {**plan['ablation'][base]['parameters'], **v['parameters']}}
    output = {'plan': plan, 'plan_hash': digest((DOCS/'experiments-plan.json').read_bytes()),
              'strategy_hash': digest(source.read_bytes()), 'data_hash': data_hash,
              'fixed_width_pct_from_first_year': fixed_pct, 'variants': variants, 'results': {}, 'selected': {}}
    save(RUNTIME/'experiments-strategy-snapshot.json', {'source': source.read_text(encoding='utf-8'),
                                                       'strategy_hash': output['strategy_hash']})
    # Selection outcomes and a locked choice are persisted before later outcomes.
    for period in ('selection', 'validation', 'recent', 'full'):
        pstart, pend = map(stamp, plan['periods'][period])
        a, b = bisect_left(times, pstart), bisect_left(times, pend)
        for key, variant in variants.items():
            module, metadata = load_strategy(source)
            parameters = validate_parameters(metadata, {**variant['parameters'], 'fixed_pct': fixed_pct, 'record_indicators': False})
            result = simulate(bars[a-650:b], module, parameters, warmup=650, step_ms=900000,
                              initial_cash=10000, position_pct=100)
            item = output['results'].setdefault(key, {})
            item[period] = describe(result)
            # Preserve every completed trade, not just favorable examples.
            save(RUNTIME/f'experiment-{key}-{period}.json', {
                'parameters': parameters, 'period': [pstart, pend], 'data_hash': data_hash,
                'strategy_hash': output['strategy_hash'], 'report': result['report'],
                'trades': result['trades'], 'signals': result['signals'],
            })
            if key in ('high_low_ema', 'ema31_atr', 'ema31_range', 'ema31_cross') and period == 'full':
                expected = read(ROOT/'.opentrading_runtime/local_backtests'/runs[key]/'result.json')
                assert result['trades'] == expected['trades'], f'Baseline trade drift: {key}'
                assert result['equity'] == expected['equity'], f'Baseline equity drift: {key}'
            print(f"{period} {key}: {result['report']['return_pct']:.2f}%, DD {result['report']['max_drawdown_pct']:.2f}%", flush=True)
        if period == 'selection':
            for base in ('high_low_ema', 'ema31_atr'):
                baseline = output['results'][base][period]
                eligible = [key for key, v in variants.items() if v.get('baseline') == base and
                            output['results'][key][period]['return_pct'] > baseline['return_pct'] and
                            output['results'][key][period]['max_drawdown_pct'] <= baseline['max_drawdown_pct'] and
                            output['results'][key][period]['total_trades'] >= 50 and
                            (output['results'][key][period]['profit_factor'] or 0) > 1]
                eligible.sort(key=lambda k: output['results'][k][period]['return_to_drawdown'], reverse=True)
                output['selected'][base] = eligible[0] if eligible else None
            save(DOCS/'experiments-selection.json', output)
            print('Locked choices: '+str(output['selected']), flush=True)
        save(DOCS/'experiments-results.json', output)
    print('Completed all 26 fixed variants across four periods; original trades/equity unchanged.', flush=True)


def publish():
    """Create a normal project run for inspecting the exploratory chase filter."""
    receipt = DOCS/'experiments-project-run.json'
    output = read(DOCS/'experiments-results.json')
    key = 'high_low_ema__distance2'
    database = build_database_runtime(settings)
    service = LocalBacktestService(database)
    try:
        if receipt.exists():
            run = service.repository.get(read(receipt)['run_id'])
        else:
            plan = read(DOCS/'plan.json')
            command = {k: plan[k] for k in ('symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct')}
            command.update(strategy='trend_cloud_experiments', parameters={
                **output['variants'][key]['parameters'], 'record_indicators': True,
                'fixed_pct': output['fixed_width_pct_from_first_year']})
            run = service.create(LocalBacktestCommand.model_validate(command))
            save(receipt, {'run_id': run['id'], 'variant': key,
                           'status_note': 'Exploratory candidate for inspection, not a first-year-selected winner.'})
        if run['status'] == 'completed':
            exact = read(service.directory(run['id'])/'result.json')
            earlier = read(RUNTIME/f'experiment-{key}-full.json')
            assert run['metadata']['data_hash'] == output['data_hash']
            assert run['metadata']['strategy_hash'] == output['strategy_hash']
            assert exact['trades'] == earlier['trades']
            assert exact['report'] == earlier['report']
            assert exact['signals'] == earlier['signals']
            save(receipt, {**read(receipt), 'verified': True, 'data_hash': output['data_hash'],
                           'strategy_hash': output['strategy_hash'], 'exact_trades_signals_report': True})
        print(json.dumps({'id': run['id'], 'status': run['status'], 'progress': run['progress'], 'error': run.get('error')}, ensure_ascii=False))
    finally:
        database.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['baseline', 'experiments', 'publish'])
    args = parser.parse_args()
    {'baseline': baseline_diagnostics, 'experiments': experiments, 'publish': publish}[args.action]()
