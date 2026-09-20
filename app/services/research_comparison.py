"""Read saved results; distinguish a controlled comparison from a ranking."""
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, median
from app.domain.backtest_diagnostics import summarize
from app.infra.research_files import encode, sha
from app.services.backtest_provenance import evidence_status

PROVENANCE_KEYS = ('environment', 'execution_bundle', 'source', 'data_hash', 'execution_data_hash',
                   'execution_alignment_hash', 'strategy_hash', 'warmup_bars')
REQUIRED_INPUTS = ('strategy', 'symbol', 'timeframe', 'start', 'end', 'initial_cash', 'position_pct', 'data_gap_policy', 'parameters')


def normalized_config(config):
    return {**{'execution_timeframe': None, 'intrabar_profit_protection': False,
               'execution_gap_policy': 'coarse_fallback'}, **config}


def flatten(value, prefix=''):
    result = {}
    for key, item in value.items():
        name = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            result.update(flatten(item, name))
        else:
            result[name] = item
    return result


def compare_runs(first, second):
    if any(r['status'] != 'completed' for r in (first, second)):
        raise ValueError('只能比较已完成结果')
    left, right = flatten(normalized_config(first['config'])), flatten(normalized_config(second['config']))
    changes = {k: {'before': left.get(k), 'after': right.get(k)} for k in sorted(left.keys() | right.keys())
               if left.get(k) != right.get(k)}
    issues = []
    provenance = [evidence_status(r) for r in (first, second)]
    for run, evidence in zip((first, second), provenance):
        if evidence['missing']:
            issues.append(f"{run['id']} 缺少版本证据：{', '.join(evidence['missing'])}")
        missing = [key for key in REQUIRED_INPUTS if key not in run['config']]
        if missing:
            issues.append(f"{run['id']} 缺少输入：{', '.join(missing)}")
    input_issues = list(issues)
    differing_evidence = []
    for key in PROVENANCE_KEYS:
        a, b = first['metadata'].get(key), second['metadata'].get(key)
        if a != b:
            issues.append(f'{key} 不同')
            differing_evidence.append(key)
    for key in ('start', 'end', 'initial_cash', 'data_gap_policy', 'symbol', 'strategy'):
        if key in changes:
            issues.append(f'{key} 不同，不能作为同条件参数效果')
    # A timeframe experiment necessarily changes aggregation and data hashes.
    # Keep it separate from an identical-data parameter effect.
    timeframe_comparison = (set(changes) == {'timeframe'} and not input_issues
        and set(differing_evidence) <= {'data_hash', 'execution_alignment_hash', 'warmup_bars'})
    execution_comparison = (set(changes) <= {'execution_timeframe', 'intrabar_profit_protection'}
        and 'execution_timeframe' in changes and not input_issues
        and set(differing_evidence) <= {'execution_data_hash', 'execution_alignment_hash'})
    return {'runs': [first['id'], second['id']], 'changes': changes, 'issues': issues, 'provenance': provenance,
            'single_factor': len(changes) == 1 and not issues,
            'timeframe_comparison': timeframe_comparison, 'execution_comparison': execution_comparison,
            'comparison_kind': 'timeframe' if timeframe_comparison else 'execution' if execution_comparison else 'parameter' if len(changes)==1 and not issues else 'uncontrolled',
            'return_difference_percentage_points': second['report']['return_pct'] - first['report']['return_pct'],
            'note': '这是两次完整回测的收益差，不是相关系数，也不自动证明某个因素导致盈利'}


def paired_effect(runs, factor):
    groups = defaultdict(list)
    seen = set()
    for run in runs:
        if run['id'] in seen or run['status'] != 'completed':
            continue
        seen.add(run['id'])
        config = flatten(normalized_config(run['config']))
        if factor not in config:
            continue
        value = config.pop(factor)
        # Different source code / datasets / capital conventions cannot masquerade
        # as a paired experiment, even if their human names happen to match.
        ignored = {'data_hash', 'execution_alignment_hash', 'warmup_bars'} if factor == 'timeframe' else {'execution_data_hash', 'execution_alignment_hash'} if factor == 'execution_timeframe' else set()
        signature = sha(encode({'config': config, 'metadata': {k: run['metadata'].get(k) for k in PROVENANCE_KEYS if k not in ignored}}))
        groups[signature].append((value, run))
    comparisons = defaultdict(list)
    for group in groups.values():
        group.sort(key=lambda x: (str(type(x[0])), x[0]))
        for i, (a, first) in enumerate(group):
            for b, second in group[i + 1:]:
                if a == b:
                    continue
                comparison = compare_runs(first, second)
                if comparison['single_factor'] or factor == 'timeframe' and comparison['timeframe_comparison'] or factor == 'execution_timeframe' and comparison['execution_comparison']:
                    comparisons[(a, b)].append(comparison)
    return {'factor': factor, 'pairs': [
        {'before': a, 'after': b, 'paired_comparisons': len(values),
         'improved': sum(v['return_difference_percentage_points'] > 0 for v in values),
         'median_return_difference_percentage_points': median(v['return_difference_percentage_points'] for v in values),
         'min_return_difference_percentage_points': min(v['return_difference_percentage_points'] for v in values),
         'max_return_difference_percentage_points': max(v['return_difference_percentage_points'] for v in values),
         'run_pairs': [v['runs'] for v in values]} for (a, b), values in comparisons.items()],
        'comparison_kind': 'timeframe' if factor == 'timeframe' else 'execution' if factor == 'execution_timeframe' else 'parameter',
        'note': '周期比较固定区间、来源和策略，聚合与行情快照随周期改变。' if factor == 'timeframe' else '成交周期比较固定主行情和策略，细行情随周期改变。' if factor == 'execution_timeframe' else '只纳入其他输入与必需快照证据相同的配对；无配对即证据不足。历史局部效果不等于永久最优。'}


def trade_breakdown(service, identifier):
    run = service.repository.get(identifier)
    if run['status'] != 'completed':
        raise ValueError('回测尚未完成')
    trades, offset = [], 0
    while True:
        batch = service.records(identifier, 'trades', offset, 2000)
        trades.extend(batch['items'])
        offset += len(batch['items'])
        if offset >= batch['total']:
            break
    groups = {key: defaultdict(list) for key in ('side', 'exit_reason', 'exit_year', 'exit_month')}
    for trade in trades:
        date = datetime.fromtimestamp(trade['exit_time'] / 1000, timezone.utc)
        for key, label in [('side', trade['side']), ('exit_reason', trade['exit_reason']),
                           ('exit_year', date.strftime('%Y')), ('exit_month', date.strftime('%Y-%m'))]:
            groups[key][label].append(trade)
    gross = sum(t['profit'] for t in trades if t['profit'] > 0)
    winners = sorted((t for t in trades if t['profit'] > 0), key=lambda t: t['profit'], reverse=True)
    return {'run_id': identifier, 'report': run['report'],
            'trade_summary': summarize(trades, include_streak=True),
            'median_holding_minutes': median(t['duration_minutes'] for t in trades) if trades else None,
            'mean_holding_minutes': mean(t['duration_minutes'] for t in trades) if trades else None,
            'top_10_gross_profit_share_pct': 100 * sum(t['profit'] for t in winners[:10]) / gross if gross else None,
            'groups': {k: {label: summarize(v) for label, v in sorted(group.items())} for k, group in groups.items()},
            'basis': '按平仓日期分组的已实现盈亏贡献，单位为账户计价币；不是年度重启收益率，也不是分段盯市收益率。持仓分钟按开平仓时间；同根K线内部时刻未知。退出原因是结算触发条件，不自动等于亏损病因。'}
