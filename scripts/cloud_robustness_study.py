"""Finite robustness experiment using only OpenTrading's data and simulator."""
import argparse
from bisect import bisect_left
from datetime import datetime, timezone
import json
from math import ceil
from pathlib import Path

import numpy as np

from app.domain.local_backtest import Bar, simulate
from app.services.local_backtest_strategies import digest, environment, load_strategy, validate_parameters
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import metrics, read, save
from scripts.trend_cloud_study import stamp

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'docs/verification/eth-cloud-robustness-20260910'
RUNTIME = ROOT/'.opentrading_runtime/cloud-robustness-20260910'
SOURCE = ROOT/'strategies/trend_cloud_robustness_v1.py'
DAY = 86400000


def prepare():
    path = DOCS/'plan.json'
    if path.exists():
        raise ValueError('Frozen plan already exists; create a new study/version instead of overwriting it')
    variants = {}

    def add(key, name, family, selectable=True, **changes):
        parameters = dict(center_length=31, width_length=31, trigger_mult=.8, activation_pct=2,
                          giveback_pct=50, entry_method='none', method_value=0, record_indicators=False)
        parameters.update(changes)
        variants[key] = dict(name=name, family=family, selectable=selectable, parameters=parameters)

    add('anchor', '上轮利润保护版：盈利 2% 启动，回吐 50%', 'reference')
    add('legacy', '早期基准：门槛 0.99，无利润保护', 'reference', trigger_mult=.99, activation_pct=0, giveback_pct=40)
    add('no_protection', '上轮门槛 0.8，无利润保护', 'reference', activation_pct=0, giveback_pct=40)
    for key, label, field, value in [
        ('width25','宽度周期 25','width_length',25), ('width40','宽度周期 40','width_length',40),
        ('trigger60','突破门槛 0.6','trigger_mult',.6), ('trigger100','突破门槛 1.0','trigger_mult',1.),
        ('activate15','浮盈 1.5% 启动','activation_pct',1.5), ('activate25','浮盈 2.5% 启动','activation_pct',2.5),
        ('giveback40','回吐 40% 平仓','giveback_pct',40), ('giveback60','回吐 60% 平仓','giveback_pct',60)]:
        add(key, label, 'neighbor', False, **{field: value})
    for n in (55, 89):
        add(f'center{n}', f'放慢中心线：EMA{n}', 'slower_center', center_length=n)
    for n in (96, 192):
        add(f'trend{n}', f'只顺较慢的 EMA{n} 方向开仓', 'trend_filter', entry_method='slow_trend', method_value=n)
    for value in (.2, .3):
        add(f'efficiency{int(value*100)}', f'过滤震荡：趋势效率至少 {int(value*100)}%', 'efficiency_filter', entry_method='efficiency', method_value=value)
    for n in (4, 16):
        add(f'spacing{n}', f'两次新入场信号至少间隔 {n/4:g} 小时', 'entry_spacing', entry_method='spacing', method_value=n)
    add('alternate', '平仓后不再连续开同向单', 'alternate', entry_method='alternate')
    boundaries = ['2025-09-10','2025-12-10','2026-03-10','2026-06-10','2026-09-10']
    train_starts = ['2024-09-10','2024-12-10','2025-03-10','2025-06-10']
    folds = [{'id': f'q{i+1}', 'train': [a+'T00:00:00Z', b+'T00:00:00Z'],
              'test': [b+'T00:00:00Z', c+'T00:00:00Z']}
             for i, (a,b,c) in enumerate(zip(train_starts, boundaries, boundaries[1:]))]
    plan = dict(created_at=datetime.now(timezone.utc).isoformat(), symbol='ETH/USDT', timeframe='15m',
                start='2024-09-10T00:00:00Z', end='2026-09-10T00:00:00Z',
                source_run='af7dce8bc6014d6ebbdfd56c380ef44b',
                data_hash='ca0edb3d7493df0da568b8cad6355a894de8c44cde82cd42c207704e3b0e90f7',
                initial_cash=10000, position_pct=100, warmup=650, variants=variants, folds=folds,
                selection_rule='Only 12 selectable references/methods. Prior rolling 12 months: positive return, PF > 1, at least 50 trades; rank return / maximum drawdown, then return, then ID. If none qualify, hold cash for the next quarter. Eight one-at-a-time neighbors are diagnostics, never additional selection choices.',
                execution='Engine v4 unchanged. Close signal / next open, two independent exits: profit protection OR raw opposite crossing. Entry filters never block an opposite-signal exit. No added fixed stop/target. No costs, no leverage. Quarterly tests start flat; force close at the last close and select again. Scale subsequent-quarter capital by preceding-quarter equity.',
                method_definitions={
                    'trend_filter': 'Close must lie above / below EMA(close,96 or 192) for long / short. These are 15-minute EMA periods, not 4-hour bars.',
                    'efficiency_filter': 'Over 32 completed bars: absolute net close change / sum of absolute consecutive close changes; require >= 0.2 or 0.3.',
                    'entry_spacing': 'At least 4 / 16 bars between accepted new entry decisions; holding same-side signals do not reset the clock. Raw opposite signals still exit.',
                    'alternate': 'An accepted new entry must have the opposite side to the last accepted entry. Therefore after profit exit no same-side re-entry; a blocked opposite entry still closes the held position.'},
                continuation_criteria={'positive_quarters_min':3,'test_return_positive':True,
                                       'max_drawdown_pct_max':25,'worst_quarter_return_pct_min':-10,
                                       'rolling_bootstrap_lower_95_positive_at_both_block_sizes':True},
                statistical_check={'replicates':2000,'seed':20260910,'block_days':[7,14],
                                   'note':'Resample consecutive daily log returns in circular blocks, not independent trades. Pointwise 95% intervals for the predeclared rolling rule. One-sided simultaneous 95% lower bounds across all 20 fixed variants against zero and against the anchor, using centered joint block resamples and a maximum statistic. Bounds are diagnostic under approximate stationarity; they do not undo prior inspection of this market history.'},
                stopping_rule='One finite round: 20 variants, four prior-year / next-quarter folds, full-history descriptions. Freeze choices before each next quarter. Do not expand the grid or substitute the hindsight winner if continuation criteria fail. Failure means stop optimizing this ETH 15m cloud strategy on this dataset; it does not prove every technical strategy impossible.',
                caveat='All two-year prices and several prior strategy studies have already been inspected. This is a retrospective robustness check, not untouched out-of-sample or prospective proof. The screenshot interval is included and is already known. Continuation thresholds are research screening rules, not a definition or guarantee of stable future profit.')
    save(path, plan)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    paths = [SOURCE, Path(__file__), ROOT/'scripts/cloud_strategy_versions.py', ROOT/'scripts/profit_protection_study.py',
             ROOT/'scripts/trend_cloud_study.py', ROOT/'app/domain/local_backtest.py', ROOT/'app/services/local_backtest_strategies.py', path]
    paths += list((ROOT/'test').glob('test_cloud_robustness.py'))
    snapshot('002-frozen-round-v1', paths)
    print(f'Frozen: {len(variants)} variants, {sum(v["selectable"] for v in variants.values())} selectable methods, four quarters.', flush=True)


def pick(training, plan):
    eligible = [key for key, r in training.items() if plan['variants'][key]['selectable'] and
                r['return_pct'] > 0 and (r['profit_factor'] or 0) > 1 and r['total_trades'] >= 50]
    return sorted(eligible, key=lambda k: (-(training[k]['return_to_drawdown'] or 0), -training[k]['return_pct'], k))


def stitched(parts, initial=10000):
    """Accounting composition only; each part was executed by the public engine."""
    capital, points, trades = initial, [], []
    for label, part in parts:
        scale = capital/part['report']['initial_cash']
        equity = part['equity']
        points.extend({'timestamp': p['timestamp'], 'equity': p['equity']*scale} for p in (equity[1:] if points else equity))
        for trade in part['trades']:
            t = dict(trade, fold=label)
            for field in ('profit','principal','quantity'):
                t[field] *= scale
            trades.append(t)
        capital = part['report']['final_equity']*scale
    values = np.array([p['equity'] for p in points])
    peak = np.maximum.accumulate(values)
    wins = [t['profit'] for t in trades if t['profit'] > 0]
    losses = [-t['profit'] for t in trades if t['profit'] < 0]
    daily = {}
    for p in points[1:]:
        day = datetime.fromtimestamp((p['timestamp']-1)/1000, timezone.utc).strftime('%Y-%m-%d')
        daily[day] = p['equity']
    returns = np.diff(np.log(np.array([initial]+list(daily.values()))))
    report = dict(initial_cash=initial, final_equity=capital, return_pct=(capital/initial-1)*100,
                  max_drawdown_pct=float(np.max((peak-values)/peak)*100), total_trades=len(trades),
                  wins=len(wins), losses=len(losses), profit_factor=sum(wins)/sum(losses) if losses else None,
                  win_rate=len(wins)/len(trades)*100 if trades else None)
    assert abs(capital-initial-sum(t['profit'] for t in trades)) < 1e-6
    return dict(report=report, daily_equity=[dict(date=d,equity=v) for d,v in daily.items()],
                daily_log_returns=returns.tolist(), trades=trades)


def block_indices(n, block, rng):
    starts = rng.integers(0, n, size=ceil(n/block))
    return ((starts[:,None]+np.arange(block))%n).ravel()[:n]


def bootstrap(matrix, rolling, replicates=2000, seed=20260910, block=7, anchor_index=0):
    """Joint, centered block bootstrap; all candidates use identical sampled days."""
    matrix, rolling = np.asarray(matrix, dtype=float), np.asarray(rolling, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != len(rolling):
        raise ValueError('Aligned daily returns required')
    rng, means = np.random.default_rng(seed+block), matrix.mean(axis=0)
    difference = matrix-matrix[:,anchor_index,None]
    dm = difference.mean(axis=0)
    max_zero, max_diff, rolling_samples = [], [], []
    for _ in range(replicates):
        idx = block_indices(len(rolling), block, rng)
        max_zero.append(float(np.max(matrix[idx].mean(axis=0)-means)))
        max_diff.append(float(np.max(difference[idx].mean(axis=0)-dm)))
        rolling_samples.append(float(rolling[idx].mean()))
    annual = lambda x: np.expm1(np.asarray(x)*365)*100
    return dict(block_days=block, replicates=replicates,
                rolling_annual_return_interval_95=annual(np.quantile(rolling_samples,[.025,.975])).tolist(),
                fixed_annual_return_simultaneous_lower_95=annual(means-np.quantile(max_zero,.95)).tolist(),
                fixed_vs_anchor_annual_relative_return_simultaneous_lower_95=annual(dm-np.quantile(max_diff,.95)).tolist())


def run():
    plan = read(DOCS/'plan.json')
    paths = [DOCS/'plan.json', SOURCE, Path(__file__), ROOT/'app/domain/local_backtest.py',
             ROOT/'scripts/profit_protection_study.py', ROOT/'scripts/trend_cloud_study.py',
             ROOT/'app/services/local_backtest_strategies.py']
    provenance = {'files': {p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in paths}, 'environment':environment()}
    data_path = ROOT/'.opentrading_runtime/local_backtests'/plan['source_run']/'data.json'
    raw = data_path.read_bytes()
    assert digest(raw) == plan['data_hash']
    provenance['data_hash'] = digest(raw)
    output_path = DOCS/'results.json'
    output = read(output_path) if output_path.exists() else dict(provenance=provenance, plan=plan, results={}, choices={}, status='running')
    if output['provenance'] != provenance:
        raise ValueError('Inputs changed. Preserve this round and make a new version; never mix results.')
    bars = [Bar(int(r[0]), *map(float,r[1:])) for r in json.loads(raw)]
    times = [b.timestamp for b in bars]

    def calculate(key, period, bounds):
        path = RUNTIME/f'{key}-{period}.json'
        if period in output['results'].get(key, {}):
            cached = read(path)
            assert cached['provenance'] == provenance
            return cached
        a,b = (bisect_left(times,stamp(t)) for t in bounds)
        assert a >= plan['warmup'] and times[a] == stamp(bounds[0])
        assert b-a == (stamp(bounds[1])-stamp(bounds[0]))//900000
        module, spec = load_strategy(SOURCE)
        params = validate_parameters(spec, plan['variants'][key]['parameters'])
        r = simulate(bars[a-plan['warmup']:b], module, params, warmup=plan['warmup'], step_ms=900000,
                     initial_cash=plan['initial_cash'], position_pct=plan['position_pct'])
        if period == 'full' and key in ('anchor','legacy','no_protection'):
            ids = {'anchor':'af7dce8bc6014d6ebbdfd56c380ef44b', 'legacy':'39db5fdae92f42e89f7556721a43a1c8',
                   'no_protection':'c02076bd6ebf4d9b906ea4587df1cae9'}
            old = read(ROOT/'.opentrading_runtime/local_backtests'/ids[key]/'result.json')
            assert r['trades'] == old['trades'] and r['equity'] == old['equity'], 'Reference behavior changed'
            output.setdefault('exact_reference_replays',[]).append(key)
        summary = metrics(r)
        output['results'].setdefault(key,{})[period] = summary
        # Complete decision/trade traces and close equity; no second simulator.
        trace = {k:r[k] for k in ('report','trades','signals','equity')}
        trace.update(provenance=provenance, parameters=params, period=bounds)
        save(path, trace)
        save(output_path, output)
        print(f'{period} {key}: {summary["return_pct"]:.2f}%, DD {summary["max_drawdown_pct"]:.2f}%, {summary["total_trades"]} trades',flush=True)
        return trace

    test_parts = {k:[] for k in plan['variants']}
    rolling_parts = []
    for fold in plan['folds']:
        training = {}
        for key,v in plan['variants'].items():
            if v['selectable']:
                calculate(key,fold['id']+'-train',fold['train'])
                training[key] = output['results'][key][fold['id']+'-train']
        ranking = pick(training,plan)
        choice = {'fold':fold, 'ranking':ranking,'selected':ranking[0] if ranking else None,'provenance':provenance}
        selection_path = DOCS/f'{fold["id"]}-choice.json'
        if selection_path.exists():
            assert read(selection_path) == choice
        else:
            save(selection_path,choice)
        output['choices'][fold['id']] = choice
        save(output_path,output)
        print(f'LOCKED {fold["id"]}: {choice["selected"]}',flush=True)
        for key in plan['variants']:
            trace = calculate(key,fold['id']+'-test',fold['test'])
            test_parts[key].append((fold['id'],trace))
        if choice['selected']:
            rolling_parts.append(test_parts[choice['selected']][-1])
        else:
            # No qualifying training strategy: cash, with matching timestamps.
            reference = test_parts['anchor'][-1][1]
            rolling_parts.append((fold['id'],dict(report={'initial_cash':10000,'final_equity':10000},trades=[],
                                                 equity=[dict(timestamp=p['timestamp'],equity=10000) for p in reference['equity']])))
    stitched_results = {k:stitched(p) for k,p in test_parts.items()}
    rolled = stitched(rolling_parts)
    save(RUNTIME/'rolling-trades.json',rolled)
    for key,result in stitched_results.items():
        save(RUNTIME/f'{key}-four-quarters.json',result)
    output['fixed_quarters'] = {k:{x:v for x,v in r.items() if x != 'trades'} for k,r in stitched_results.items()}
    output['rolling'] = {x:v for x,v in rolled.items() if x != 'trades'}
    for key in plan['variants']:
        calculate(key,'full',[plan['start'],plan['end']])
    keys = list(plan['variants'])
    dates = [d['date'] for d in rolled['daily_equity']]
    assert len(dates) == 365 and all([d['date'] for d in stitched_results[k]['daily_equity']] == dates for k in keys)
    matrix = np.array([stitched_results[k]['daily_log_returns'] for k in keys]).T
    stats = plan['statistical_check']
    output['bootstrap'] = {str(block):bootstrap(matrix,rolled['daily_log_returns'],stats['replicates'],stats['seed'],block,keys.index('anchor')) for block in stats['block_days']}
    quarter_returns = [p['report']['return_pct'] if 'return_pct' in p['report'] else 0 for _,p in rolling_parts]
    c = plan['continuation_criteria']
    checks = {'return_positive':rolled['report']['return_pct'] > 0,
              'positive_quarters':sum(r > 0 for r in quarter_returns) >= c['positive_quarters_min'],
              'drawdown':rolled['report']['max_drawdown_pct'] <= c['max_drawdown_pct_max'],
              'worst_quarter':min(quarter_returns) >= c['worst_quarter_return_pct_min'],
              'bootstrap_lower_bound':all(r['rolling_annual_return_interval_95'][0] > 0 for r in output['bootstrap'].values())}
    output['decision'] = dict(checks=checks,continue_research=all(checks.values()),quarter_returns=quarter_returns,
                             rule='Apply predeclared criteria to the rolling selection rule, never replace it with the best retrospective parameter.')
    output['retrospective_best'] = max(keys,key=lambda k:stitched_results[k]['report']['return_pct'])
    output['completed_simulations'] = sum(len(v) for v in output['results'].values())
    output['status'] = 'completed'
    save(output_path,output)
    print(json.dumps({'decision':output['decision'],'rolling':rolled['report'],'retrospective_best':output['retrospective_best'],'simulations':output['completed_simulations']},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run'])
    args = parser.parse_args()
    prepare() if args.action == 'prepare' else run()
