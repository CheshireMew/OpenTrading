"""Past-only selection and scheduled switching around the existing cloud strategy.

The canonical simulator still owns orders, stops, fine-candle protection and cash.
Selection changes are decided at a completed close and liquidate at the next open.
"""
from bisect import bisect_right
from dataclasses import replace
from math import log
from app.domain.local_backtest import BarResult, Intent


def past_score(trace, lo, hi, *, step=900000, fine_step=300000, fallback=()):
    times = [p['timestamp'] for p in trace['equity']]
    a, b = bisect_right(times, lo)-1, bisect_right(times, hi)-1
    assert a >= 0 and times[a] == lo and times[b] == hi
    eq = trace['equity']
    growth = eq[b]['equity']/eq[a]['equity']
    closed = 0
    for t in trace['trades']:
        if t['entry_time'] < lo or t['exit_time'] >= hi or t['exit_reason'] == 'end_of_backtest':
            continue
        # An intrabar exit is only knowable when that observed candle closes.
        available = t['exit_time']
        if t['exit_phase'] == 'close':
            available += step
        elif t['exit_phase'] == 'intrabar':
            available += step if available//step*step in fallback else fine_step
        closed += available <= hi
    return dict(return_pct=100*(growth-1), log_return=log(growth), closed_trades=closed)


def choose(scores, minimum=20):
    eligible = [k for k,v in scores.items() if v['return_pct']>0 and v['closed_trades']>=minimum]
    eligible.sort(key=lambda k:(-scores[k]['log_return'], k))
    return dict(chosen=eligible[0] if eligible else None, eligible=len(eligible))


class ScheduledCloud:
    def __init__(self, calculation_type, candidates, decisions, *, start, step=900000):
        assert decisions and decisions[0]['at'] == start
        assert [d['at'] for d in decisions] == sorted(set(d['at'] for d in decisions))
        assert all(d['chosen'] is None or d['chosen'] in candidates for d in decisions)
        self.calcs = {k:calculation_type(v) for k,v in candidates.items()}
        self.review = {d['at']:d['chosen'] for d in decisions[1:]}
        self.chosen = decisions[0]['chosen']
        self.start, self.step, self.processed = start, step, 0
        self.transitions = []

    def on_bar(self, context):
        result = None
        for i in range(self.processed, len(context.history)):
            bar = context.history[i]
            last = i == len(context.history)-1
            for key, calc in self.calcs.items():
                value = calc.update(bar, context.position if last else None,
                    context.last_exit if last else None, decisions=last and key==self.chosen)
                if last and key==self.chosen:
                    result = value
        self.processed = len(context.history)
        at = context.history[-1].timestamp+self.step
        if at in self.review and self.review[at] != self.chosen:
            old, new = self.chosen, self.review[at]
            self.transitions.append(dict(at=at, old=old, new=new, held=context.position is not None))
            for key in (old, new):
                if key is not None:
                    c = self.calcs[key]
                    c.waiting = c.active = c.handled_exit = None
            self.chosen = new
            result = result or BarResult()
            # Discard the old close's entry order. A new setup must observe its
            # own first completed candle before creating a confirmation order.
            result = replace(result, intent=Intent('close', reason='parameter_change') if context.position else None,
                entry_order=None, checks={**result.checks, '参数切换': True})
        return result
