"""Strategy-independent statistics over saved account marks and trades."""
from datetime import datetime, timezone
from math import fsum, isclose


def calendar_bound(timestamp, kind):
    date = datetime.fromtimestamp(timestamp/1000, timezone.utc)
    if kind == 'year':
        start, end = datetime(date.year, 1, 1, tzinfo=timezone.utc), datetime(date.year+1, 1, 1, tzinfo=timezone.utc)
        label = str(date.year)
    elif kind == 'month':
        start = datetime(date.year, date.month, 1, tzinfo=timezone.utc)
        end = datetime(date.year+(date.month == 12), date.month % 12+1, 1, tzinfo=timezone.utc)
        label = date.strftime('%Y-%m')
    else:
        raise ValueError('周期应为 year 或 month')
    return label, int(start.timestamp()*1000), int(end.timestamp()*1000)


def calendar_returns(points, kind):
    """Account marks at UTC boundaries; missing boundaries carry the prior mark.

    Ending exactly at January 1 belongs to the preceding year's close. Returns
    are continuous account growth, including unrealized profit and position size.
    """
    iterator = iter(points)
    first = next(iterator, None)
    if first is None:
        return []
    start, initial = first['timestamp'], first['equity']
    last = first
    label, nominal_start, boundary = calendar_bound(start, kind)
    initial_mark = first['timestamp']
    output = []
    def close(end, mark):
        if end > start:
            output.append(dict(label=label, start=start, end=end, start_equity=initial, end_equity=mark['equity'],
                return_pct=100*(mark['equity']/initial-1) if initial > 0 else None,
                start_mark_time=initial_mark, end_mark_time=mark['timestamp'],
                partial=start != nominal_start or end != boundary,
                boundary_carried=start != initial_mark or end != mark['timestamp']))
    for point in iterator:
        if point['timestamp'] < last['timestamp']:
            raise ValueError('权益记录时间顺序错误')
        while point['timestamp'] >= boundary:
            mark = point if point['timestamp'] == boundary else last
            close(boundary, mark)
            start, initial, initial_mark = boundary, mark['equity'], mark['timestamp']
            label, nominal_start, boundary = calendar_bound(start, kind)
        last = point
    close(last['timestamp'], last)
    return output


def drawdown_episodes(points):
    """Peak, trough and recovery from account marks, with no inferred intrabar path."""
    peak = None
    current = None
    episodes = []
    last = None
    for point in points:
        if last is not None and point['timestamp'] < last['timestamp']:
            raise ValueError('权益记录时间顺序错误')
        if peak is None or point['equity'] >= peak['equity'] or isclose(point['equity'], peak['equity'], rel_tol=1e-12):
            if current is not None:
                current.update(recovery_time=point['timestamp'], end_time=point['timestamp'], recovered=True,
                    duration_ms=point['timestamp']-current['peak_time'],
                    recovery_duration_ms=point['timestamp']-current['trough_time'])
                episodes.append(current)
                current = None
            peak = point
        elif peak['equity'] > 0:
            if current is None:
                current = dict(peak_time=peak['timestamp'], peak_equity=peak['equity'],
                               trough_time=point['timestamp'], trough_equity=point['equity'])
            if point['equity'] < current['trough_equity']:
                current.update(trough_time=point['timestamp'], trough_equity=point['equity'])
            current['drawdown_pct'] = 100*(1-current['trough_equity']/peak['equity'])
        last = point
    if current is not None:
        current.update(recovery_time=None, end_time=last['timestamp'], recovered=False,
                       duration_ms=last['timestamp']-current['peak_time'], recovery_duration_ms=None)
        episodes.append(current)
    return dict(episodes=episodes, max_drawdown=max(episodes, key=lambda e: e['drawdown_pct'], default=None),
                longest=max(episodes, key=lambda e: e['duration_ms'], default=None),
                unrecovered=episodes[-1] if episodes and not episodes[-1]['recovered'] else None,
                basis='仅按保存的收盘权益确认高点、谷底与恢复；没有推断 K 线内部价格顺序。')


def normalized_trades(trades, principal=10000):
    if principal <= 0:
        raise ValueError('等额本金必须大于零')
    values = [t['return_pct'] for t in trades]
    winners = sorted((r for r in values if r > 0), reverse=True)
    losses = [r for r in values if r < 0]
    gross_win = fsum(winners)*principal/100
    gross_loss = -fsum(losses)*principal/100
    return dict(principal_per_trade=principal, trades=len(values), wins=len(winners), losses=len(losses),
                gross_profit=gross_win, gross_loss=gross_loss, net_profit=gross_win-gross_loss,
                profit_factor=gross_win/gross_loss if gross_loss else None,
                top_1_gross_profit_share_pct=100*winners[0]/fsum(winners) if winners else None,
                top_10_gross_profit_share_pct=100*fsum(winners[:10])/fsum(winners) if winners else None,
                basis='每笔按相同入场本金换算，保留全部真实交易，不复利、不改变仓位路径；不是策略重新模拟的账户收益。')


def compare_trades(before, after, *, offset=0, limit=100):
    """Match exact entry time, side and occurrence; never align by nearest time."""
    from collections import defaultdict
    def index(trades):
        grouped = defaultdict(list)
        for t in trades:
            grouped[(t['entry_time'], t['side'])].append(t)
        return {(time, side, n): t for (time, side), rows in grouped.items() for n, t in enumerate(rows)}
    left, right = index(before), index(after)
    changes, unchanged = [], 0
    fields = ('entry_price', 'exit_time', 'exit_phase', 'exit_price', 'exit_reason', 'return_pct', 'entry_ambiguity_policy')
    def same(field, a, b):
        if field in {'entry_price', 'exit_price', 'return_pct'} and isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
        return a == b
    for key in sorted(left.keys() | right.keys()):
        a, b = left.get(key), right.get(key)
        changed = [f for f in fields if a and b and not same(f, a.get(f), b.get(f))]
        if a and b and not changed:
            unchanged += 1
            continue
        changes.append(dict(kind='added' if a is None else 'dropped' if b is None else 'changed',
                            entry_time=key[0], side=key[1], occurrence=key[2], before=a, after=b, changed_fields=changed))
    removed = [c['before'] for c in changes if c['kind'] == 'dropped']
    added = [c['after'] for c in changes if c['kind'] == 'added']
    return dict(total=len(changes), offset=offset, items=changes[offset:offset+limit], unchanged=unchanged,
                added=normalized_trades(added), dropped=normalized_trades(removed),
                changed=sum(c['kind'] == 'changed' for c in changes),
                note='按准确开仓时刻、方向及同刻次序匹配；更早或更晚开仓分别列为增加与减少，不强行推断为同一笔。价格与收益率忽略 1e-12 级浮点误差。盈亏比较用等额本金；账户资金变化本身不算交易规则变化。')
