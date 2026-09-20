"""One read path for account diagnostics, exact trade differences and lineage."""
from app.domain.account_diagnostics import calendar_returns, drawdown_episodes, normalized_trades, compare_trades
from app.services.research_comparison import trade_breakdown, compare_runs
from app.domain.market.constants import timeframe_to_milliseconds


class BacktestDiagnosticsService:
    def __init__(self, backtests):
        self.backtests = backtests

    def completed(self, identifier):
        run = self.backtests.repository.get(identifier)
        if run['status'] != 'completed':
            raise ValueError('只能诊断已完成结果')
        return run

    def rows(self, identifier, kind, start=None, end=None):
        offset = 0
        while True:
            page = self.backtests.records(identifier, kind, offset, 2000, start, end)
            yield from page['items']
            offset += len(page['items'])
            if offset >= page['total'] or not page['items']:
                return

    def summary(self, identifier, *, equity_kind='equity'):
        run = self.completed(identifier)
        if equity_kind not in {'equity', 'execution_equity'}:
            raise ValueError('权益类型应为 equity 或 execution_equity')
        breakdown = trade_breakdown(self.backtests, identifier)
        count = self.backtests.records(identifier, equity_kind, 0, 1)['total']
        if not count:
            return dict(**breakdown, equity_kind=equity_kind, available=False, annual=[], monthly=[], drawdown={},
                        normalized=normalized_trades(list(self.rows(identifier, 'trades'))),
                        account_basis='这份旧结果没有保存所选频率的权益；不能用主周期曲线冒充细周期回撤。')
        def points():
            from datetime import datetime
            rows = iter(self.rows(identifier, equity_kind))
            first = next(rows, None)
            start = int(datetime.fromisoformat(run['config']['start'].replace('Z', '+00:00')).timestamp()*1000)
            if first and first['timestamp'] > start:
                yield {'timestamp': start, 'equity': run['config']['initial_cash']}
            if first:
                yield first
            yield from rows
        drawdown = drawdown_episodes(points())
        episodes = drawdown.pop('episodes')
        drawdown.update(total_episodes=len(episodes), worst_episodes=sorted(episodes, key=lambda e:e['drawdown_pct'], reverse=True)[:20])
        return dict(**breakdown, equity_kind=equity_kind, available=True,
                    annual=calendar_returns(points(), 'year'),
                    monthly=calendar_returns(points(), 'month'), drawdown=drawdown,
                    normalized=normalized_trades(list(self.rows(identifier, 'trades'))),
                    account_basis='UTC 连续账户收盘权益，包含持仓浮盈和实际仓位。边界没有记录时沿用边界前最后一笔权益，并标注该记录时刻；不是每年重启，也不是按平仓年份累加收益。')

    def compare(self, first, second, offset=0, limit=100):
        if offset < 0 or not 1 <= limit <= 1000:
            raise ValueError('分页范围无效')
        left, right = self.completed(first), self.completed(second)
        return dict(comparison=compare_runs(left, right),
                    **compare_trades(list(self.rows(first, 'trades')), list(self.rows(second, 'trades')), offset=offset, limit=limit))

    def timeline(self, identifier, trade_id, offset=0, limit=100):
        run = self.completed(identifier)
        if trade_id < 1 or offset < 0 or not 1 <= limit <= 1000:
            raise ValueError('交易编号或分页范围无效')
        trade = next((t for t in self.rows(identifier, 'trades') if t['trade_id'] == trade_id), None)
        if trade is None:
            raise ValueError('交易不存在')
        entry_id = trade.get('entry_signal_id')
        signal_time = trade.get('entry_order_signal_time')
        all_signals = list(self.rows(identifier, 'signals'))
        signals = [s for s in all_signals if (entry_id is not None and s.get('signal_id') == entry_id)
                   or (signal_time is not None and s.get('timestamp') == signal_time and s.get('action') == trade['side'])]
        signal_ids = {s['signal_id'] for s in signals if s.get('signal_id') is not None}
        if entry_id is not None:
            signal_ids.add(entry_id)
        start = min([trade['entry_time']] + [s['timestamp'] for s in signals])
        step = timeframe_to_milliseconds(run['config']['timeframe'])
        # A close at the first fine-bar open may leave a sibling breakout order
        # waiting for the rest of the signal bar. Include its full validity bar.
        end = max(trade['exit_time'] + (trade.get('exit_resolution_ms') or step),
                  (trade['exit_time']//step + 1)*step)
        events = list(self.rows(identifier, 'events', start, end))
        fills = [f for f in self.rows(identifier, 'fills', start, end) if f.get('trade_id') == trade_id]
        signal_ids.update(e['signal_id'] for e in events + fills if e.get('trade_id') == trade_id and e.get('signal_id') is not None)
        close_decisions = {s['decision_time'] for s in all_signals
                           if s.get('signal_id') in signal_ids and s.get('action') == 'close' and s.get('decision_time') is not None}
        signal_ids.update(s['signal_id'] for s in all_signals if s.get('signal_id') is not None
                          and s.get('order_type') == 'stop_entry' and s.get('decision_time') in close_decisions)
        events = [e for e in events if e.get('trade_id') == trade_id or e.get('signal_id') in signal_ids and e.get('signal_id') is not None]
        linked = [s for s in all_signals if s.get('signal_id') in signal_ids and s.get('signal_id') is not None]
        if linked:
            signals = linked
        has_events = bool(events)
        if has_events:
            decision_bars = {s['timestamp'] for s in signals}
            for observation in self.rows(identifier, 'indicators', start, end):
                if observation['timestamp'] in decision_bars:
                    events.append(dict(event='strategy_observation', timestamp=observation['timestamp']+step,
                                       signal_bar_time=observation['timestamp'], values=observation.get('values', {}),
                                       checks=observation.get('checks', {})))
        if not events:
            events = [{'event': 'saved_fill', **f} for f in fills]
        events.sort(key=lambda e:(e['timestamp'], e.get('event_id', 0)))
        return dict(run_id=identifier, trade=trade, signals=signals, fills=fills, total=len(events), offset=offset,
                    items=events[offset:offset+limit], lineage='recorded_events' if has_events else 'legacy_fills',
                    fallback_intervals=trade.get('execution_fallback_times'),
                    limitations=[] if has_events else ['旧版本没有状态事件；这里只显示确实保存的信号和成交，不能补造当时为何等待或拒绝反手。'],
                    basis='事件保留原始时间与阶段。盘中时间代表所在 K 线区间，不是逐笔成交时刻；保护更新时间及生效时间以保存事件为准。')
