"""Read saved results; distinguish a controlled comparison from a ranking."""
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, median
from app.domain.backtest_diagnostics import summarize
from app.infra.research_files import encode, sha


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
    left, right = flatten(first['config']), flatten(second['config'])
    changes = {k: {'before': left.get(k), 'after': right.get(k)} for k in sorted(left.keys() | right.keys())
               if left.get(k) != right.get(k)}
    issues = []
    for key in ('environment', 'engine_code_hash', 'source', 'data_hash', 'strategy_hash', 'warmup_bars'):
        a, b = first['metadata'].get(key), second['metadata'].get(key)
        if a != b:
            issues.append(f'{key} 不同')
    for key in ('start', 'end', 'initial_cash', 'position_pct', 'data_gap_policy', 'symbol'):
        if key in changes:
            issues.append(f'{key} 不同，不能作为同条件参数效果')
    return {'runs': [first['id'], second['id']], 'changes': changes, 'issues': issues,
            'single_factor': len(changes) == 1 and not issues,
            'return_difference_percentage_points': second['report']['return_pct'] - first['report']['return_pct'],
            'note': '这是两次完整回测的收益差，不是相关系数，也不自动证明某个因素导致盈利'}


def paired_effect(runs, factor):
    groups = defaultdict(list)
    seen = set()
    for run in runs:
        if run['id'] in seen or run['status'] != 'completed':
            continue
        seen.add(run['id'])
        config = flatten(run['config'])
        if factor not in config:
            continue
        value = config.pop(factor)
        # Different source code / datasets / capital conventions cannot masquerade
        # as a paired experiment, even if their human names happen to match.
        signature = sha(encode({'config': config, 'metadata': {k: run['metadata'].get(k) for k in
                             ('environment', 'engine_code_hash', 'source', 'data_hash', 'strategy_hash', 'warmup_bars')}}))
        groups[signature].append((value, run))
    comparisons = defaultdict(list)
    for group in groups.values():
        group.sort(key=lambda x: (str(type(x[0])), x[0]))
        for i, (a, first) in enumerate(group):
            for b, second in group[i + 1:]:
                if a == b:
                    continue
                comparison = compare_runs(first, second)
                if comparison['single_factor']:
                    comparisons[(a, b)].append(comparison)
    return {'factor': factor, 'pairs': [
        {'before': a, 'after': b, 'paired_comparisons': len(values),
         'improved': sum(v['return_difference_percentage_points'] > 0 for v in values),
         'median_return_difference_percentage_points': median(v['return_difference_percentage_points'] for v in values),
         'min_return_difference_percentage_points': min(v['return_difference_percentage_points'] for v in values),
         'max_return_difference_percentage_points': max(v['return_difference_percentage_points'] for v in values),
         'run_pairs': [v['runs'] for v in values]} for (a, b), values in comparisons.items()],
        'note': '只纳入其他输入和快照完全相同的配对；无配对即证据不足。历史局部效果不等于永久最优。'}


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
