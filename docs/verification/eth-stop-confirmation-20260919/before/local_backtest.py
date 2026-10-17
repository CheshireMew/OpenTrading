"""Public, causal strategy API and deterministic single-instrument simulator."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, asdict, field
from math import isfinite, isclose
from types import MappingProxyType
from typing import Any, Callable

ENGINE_VERSION = "9"
DISCLAIMER = "基于所选价格数据、不计成本的多空策略模拟"


@dataclass(frozen=True)
class Bar:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class History(Sequence):
    """Append-only past data. A strategy never receives future bars."""
    def __init__(self, past_bars):
        self.__bars = past_bars

    def __len__(self):
        return len(self.__bars)

    def __getitem__(self, key):
        value = self.__bars[key]
        return tuple(value) if isinstance(key, slice) else value


@dataclass(frozen=True)
class ProfitProtection:
    """Activate after a favorable return, then retain a share of peak profit.

    Both fields are percentages: activation_pct=2, giveback_pct=40 means
    activate at +2% and protect 60% of the best excursion known at a close.
    """
    activation_pct: float
    giveback_pct: float


@dataclass(frozen=True)
class Intent:
    action: str = "hold"
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    reason: str = ""
    profit_protection: ProfitProtection | None = None
    # Absolute price distance known at signal close, anchored to the next fill.
    # Mutually exclusive with stop_loss_pct. Used for ATR-based initial stops.
    stop_loss_distance: float | None = None


@dataclass(frozen=True)
class TrendCloud:
    upper: float
    lower: float
    bullish: bool


@dataclass(frozen=True)
class StopEntry:
    """A close-created breakout order, valid for the next observed bar only.

    Only opens when flat. A separate close intent can exit at that bar's open.
    worst_price cancels the bar's order if the open gaps beyond the chase cap.
    Ambiguous entry-bar stops use stop_first or adverse_extreme_before_entry;
    these are OHLC execution assumptions, not known tick chronology.
    """
    intent: Intent
    trigger_price: float
    worst_price: float | None = None
    ambiguity_policy: str = "stop_first"


def validate_stop_entry(order):
    if not isinstance(order, StopEntry) or not isinstance(order.intent, Intent) or order.intent.action not in ('long', 'short'):
        raise ValueError('entry_order 必须是包含 long/short Intent 的 StopEntry')
    for name in ('trigger_price', 'worst_price'):
        value = getattr(order, name)
        if value is None and name == 'worst_price':
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
            raise ValueError(f'{name} 必须是有限正数')
    d = 1 if order.intent.action == 'long' else -1
    if order.worst_price is not None and d*(order.worst_price-order.trigger_price) < 0:
        raise ValueError('入场追价上限不能在触发价之前')
    if order.ambiguity_policy not in ('stop_first', 'adverse_extreme_before_entry'):
        raise ValueError('未知的入场当根先后顺序假设')
    risk = order.intent
    for name in ('stop_loss_pct', 'take_profit_pct', 'trailing_stop_pct'):
        value = getattr(risk, name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 < value < 100):
            raise ValueError(f'{name} 必须介于 0 和 100 之间')
    distance = risk.stop_loss_distance
    if distance is not None:
        if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not isfinite(distance) or distance <= 0:
            raise ValueError('stop_loss_distance 必须是有限正数')
        if risk.stop_loss_pct is not None:
            raise ValueError('初始止损百分比与绝对距离不能同时设置')
    if risk.profit_protection is not None:
        if not isinstance(risk.profit_protection, ProfitProtection):
            raise ValueError('profit_protection 必须是 ProfitProtection')
        for name in ('activation_pct', 'giveback_pct'):
            value = getattr(risk.profit_protection, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 < value < 100:
                raise ValueError(f'profit_protection.{name} 必须介于 0 和 100 之间')


@dataclass(frozen=True)
class BarResult:
    """Optional per-close observations. Recorded even without a trade signal."""
    intent: Intent | None = None
    values: dict[str, float | None] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    cloud: TrendCloud | None = None
    entry_order: StopEntry | None = None


def observation_record(result: BarResult, timestamp: int) -> dict:
    if not isinstance(result.values, dict) or not isinstance(result.checks, dict):
        raise ValueError("指标值和条件必须是字典")
    for name, value in result.values.items():
        if not isinstance(name, str) or (value is not None and
                (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value))):
            raise ValueError(f"指标 {name} 必须是有限数值或 None")
    if any(not isinstance(k, str) or not isinstance(v, bool) for k, v in result.checks.items()):
        raise ValueError("指标条件必须使用名称和布尔值")
    cloud = result.cloud
    if cloud is not None and (not isinstance(cloud, TrendCloud) or
            not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in (cloud.upper, cloud.lower)) or
            cloud.upper < cloud.lower or not isinstance(cloud.bullish, bool)):
        raise ValueError("云带必须包含有限的上下沿与布尔方向，且上沿不能低于下沿")
    return {"timestamp": timestamp, "values": dict(result.values), "checks": dict(result.checks),
            "cloud": asdict(cloud) if cloud else None}


@dataclass(frozen=True)
class Context:
    history: History
    position: Any
    cash: float
    equity: float
    parameters: Any
    # Last completed exit, visible only after execution and before this close's
    # decision. Includes same-entry-bar stops; strategies must consume trade_id
    # once. Primitive, immutable fields only; no future fills or mutable ledger.
    last_exit: Any = None


def validate_bars(rows, start_ms, end_ms, step_ms, warmup, now_ms):
    if start_ms % step_ms or end_ms % step_ms:
        raise ValueError("起止时间必须对齐所选周期")
    if end_ms > now_ms or end_ms <= start_ms:
        raise ValueError("结束时间必须晚于开始且不能包含未收盘 K 线")
    expected_start = start_ms - warmup * step_ms
    expected_count = (end_ms - expected_start) // step_ms
    if len(rows) != expected_count:
        raise ValueError(f"历史或预热数据不足：需要 {expected_count} 根，实际 {len(rows)} 根")
    result = []
    for i, row in enumerate(rows):
        if len(row) != 6 or not all(isfinite(float(v)) for v in row):
            raise ValueError(f"非法行情字段：第 {i} 根")
        t, o, h, l, c, v = row
        if t != expected_start + i * step_ms:
            raise ValueError(f"K 线缺口、重复或未对齐：{t}")
        if min(o, h, l, c) <= 0 or v < 0 or not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError(f"非法 OHLC：{t}")
        result.append(Bar(int(t), float(o), float(h), float(l), float(c), float(v)))
    return result


def simulate(bars: list[Bar], strategy, parameters: dict, *, warmup: int,
             initial_cash: float = 10000, position_pct: float = 100,
             step_ms: int = 3600000, progress: Callable | None = None,
             execution_bars: dict[int, list[Bar]] | None = None,
             intrabar_profit_protection: bool = False,
             execution_step_ms: int | None = None, record_factory=None) -> dict:
    if intrabar_profit_protection and execution_bars is None:
        raise ValueError('盘中利润保护需要细周期成交行情')
    cash, peak = initial_cash, initial_cash
    position = None
    pending = None
    pending_entry = None
    records = record_factory or (lambda kind: [])
    trades, signals, fills, points, levels = [records(k) for k in ('trades', 'signals', 'fills', 'equity', 'levels')]
    observations = records('indicators')
    events, execution_points = records('events'), records('execution_equity')
    execution_peak = initial_cash
    resolution_ms, fallback_time = step_ms, None
    detailed_candles = fallback_candles = 0
    past_bars = []
    history = History(past_bars)
    params = MappingProxyType(dict(parameters))

    def equity(price):
        if position is None:
            return cash
        return cash + position["principal"] + position["quantity"] * (price - position["entry_price"]) * position["direction"]

    def event(kind, timestamp, **values):
        events.append({'event_id': len(events)+1, 'event': kind, 'timestamp': timestamp, **values})

    def close(price, bar, phase, reason, ambiguous=False, origin_signal=None):
        nonlocal cash, position
        pnl = position["quantity"] * (price - position["entry_price"]) * position["direction"]
        cash += position["principal"] + pnl
        trades.append({**position, "exit_price": price, "exit_time": bar.timestamp,
                        "exit_phase": phase, "exit_reason": reason, "ambiguous": ambiguous or position.get('entry_bar_ambiguous', False),
                        "exit_resolution_ms": resolution_ms,
                       "profit": pnl, "return_pct": pnl / position["principal"] * 100,
                       "duration_minutes": (bar.timestamp + (step_ms if phase == "close" else 0) - position["entry_time"]) / 60000})
        fills.append({"timestamp": bar.timestamp, "phase": phase, "action": "close", "price": price,
                      "quantity": position["quantity"], "trade_id": position["trade_id"], "reason": reason,
                      "signal_id": origin_signal.get('signal_id') if origin_signal else None})
        event('exit', bar.timestamp + (step_ms if phase == 'close' else 0),
              trade_id=position['trade_id'], phase=phase, price=price, reason=reason,
              signal_id=origin_signal.get('signal_id') if origin_signal else None,
              resolution_ms=resolution_ms, fallback=fallback_time is not None)
        position = None

    def enter(intent, bar, price, phase="open", order_signal=None, origin_signal=None):
        nonlocal cash, position
        if cash <= 0:
            return False
        principal = cash * position_pct / 100
        cash -= principal
        d = 1 if intent.action == "long" else -1
        fixed = price * (1 - d * intent.stop_loss_pct / 100) if intent.stop_loss_pct else None
        if intent.stop_loss_distance is not None:
            fixed = price - d * intent.stop_loss_distance
            if fixed <= 0:
                raise ValueError('初始绝对距离止损价必须大于0')
        trailing = price * (1 - d * intent.trailing_stop_pct / 100) if intent.trailing_stop_pct else None
        stops = [x for x in (fixed, trailing) if x is not None]
        position = {"trade_id": len(trades) + 1, "side": intent.action, "direction": d,
                    "entry_time": bar.timestamp, "entry_price": price, "principal": principal,
                    "quantity": principal / price, "stop": (max(stops) if d == 1 else min(stops)) if stops else None,
                    "target": price * (1 + d * intent.take_profit_pct / 100) if intent.take_profit_pct else None,
                    "trailing_pct": intent.trailing_stop_pct, "best": price,
                    "entry_resolution_ms": resolution_ms,
                    "execution_fallback_times": [fallback_time] if fallback_time is not None else []}
        signal_ref = order_signal or origin_signal
        position['entry_signal_id'] = signal_ref.get('signal_id') if signal_ref else None
        if intent.profit_protection is not None:
            position.update(profit_protection=asdict(intent.profit_protection),
                            profit_peak_pct=0., protection_active=False)
        if order_signal is not None:
            position.update(entry_phase=phase, entry_order_signal_time=order_signal['timestamp'],
                            entry_trigger=order_signal['trigger_price'], entry_worst_price=order_signal['worst_price'],
                            entry_ambiguity_policy=order_signal['ambiguity_policy'], entry_bar_ambiguous=False)
        fills.append({"timestamp": bar.timestamp, "phase": phase, "action": intent.action, "price": price,
                      "quantity": position["quantity"], "trade_id": position["trade_id"], "reason": intent.reason,
                      "signal_id": position['entry_signal_id']})
        event('entry', bar.timestamp, trade_id=position['trade_id'], signal_id=position['entry_signal_id'],
              phase=phase, side=intent.action, price=price, stop=position['stop'],
              resolution_ms=resolution_ms, fallback=fallback_time is not None)
        return True

    def record_levels(bar):
        if position and (not levels or (levels[-1]["timestamp"], levels[-1]["trade_id"]) != (bar.timestamp, position["trade_id"])):
            levels.append({"timestamp": bar.timestamp, "trade_id": position["trade_id"],
                           "stop": position["stop"], "target": position["target"]})

    def thresholds(bar, gap=False):
        if position is None:
            return
        stop, target, d = position["stop"], position["target"], position["direction"]
        low, high = (bar.open, bar.open) if gap else (bar.low, bar.high)
        def below(a, b):
            return a < b or isclose(a, b, rel_tol=1e-12)
        stopped = stop is not None and (below(low, stop) if d == 1 else below(stop, high))
        gained = target is not None and (below(target, high) if d == 1 else below(low, target))
        if (not gap and stopped and position.get('entry_phase') == 'intrabar'
                and position['entry_time'] == bar.timestamp
                and d*(bar.close-stop) > 0 and not isclose(bar.close, stop, rel_tol=1e-12)):
            # The adverse extreme may have happened before the breakout entry.
            # Closing beyond the stop on the adverse side, in contrast, proves
            # that the stop was crossed after entry and cannot be skipped.
            position['entry_bar_ambiguous'] = True
            if position['entry_ambiguity_policy'] == 'adverse_extreme_before_entry':
                stopped = False
        if stopped or gained:
            price = bar.open if gap else stop if stopped else target
            close(price, bar, "open" if gap else "intrabar",
                  position.get("stop_source", "stop_loss") if stopped else "take_profit", stopped and gained)

    def update_protection(bar):
        before = position.get('stop') if position else None
        if position and position["trailing_pct"]:
            d = position["direction"]
            position["best"] = max(position["best"], bar.high) if d == 1 else min(position["best"], bar.low)
            updated = position["best"] - d * position["entry_price"] * position["trailing_pct"] / 100
            if position.get("profit_protection") and (position["stop"] is None or d*(updated-position["stop"]) > 0):
                position["stop_source"] = "stop_loss"
            position["stop"] = max(position["stop"], updated) if d == 1 else min(position["stop"], updated)
        if position and position.get("profit_protection"):
            d, entry = position["direction"], position["entry_price"]
            position["best"] = max(position["best"], bar.high) if d == 1 else min(position["best"], bar.low)
            peak_profit = max(0., d*(position["best"]-entry))
            position["profit_peak_pct"] = peak_profit/entry*100
            protection = position["profit_protection"]
            activation = protection["activation_pct"]
            if position["profit_peak_pct"] > activation or isclose(position["profit_peak_pct"], activation, rel_tol=1e-12):
                position["protection_active"] = True
                updated = entry+d*peak_profit*(1-protection["giveback_pct"]/100)
                if position["stop"] is None or d*(updated-position["stop"]) > 0:
                    position["stop"] = updated
                    position["stop_source"] = "profit_protection"
        if position and position.get('stop') != before:
            event('protection_updated', bar.timestamp+resolution_ms, trade_id=position['trade_id'],
                  previous_stop=before, stop=position['stop'], effective_from=bar.timestamp+resolution_ms,
                  reason=position.get('stop_source', 'stop_loss'), resolution_ms=resolution_ms)

    for i, bar in enumerate(bars):
        past_bars.append(bar)
        if i < warmup:
            continue
        if not points:
            points.append({"timestamp": bar.timestamp, "equity": cash, "cash": cash, "unrealized": 0., "drawdown_pct": 0.})
        detail = execution_bars.get(bar.timestamp) if execution_bars is not None else None
        resolution_ms = (execution_step_ms or step_ms//len(detail)) if detail else step_ms
        fallback_time = bar.timestamp if execution_bars is not None and not detail else None
        if position and fallback_time is not None:
            position['execution_fallback_times'].append(fallback_time)
        if execution_bars is not None:
            if detail: detailed_candles += 1
            else: fallback_candles += 1
            if not execution_points:
                execution_points.append({**points[0], 'resolution_ms': resolution_ms, 'fallback': fallback_time is not None})
        active_entry, pending_entry = pending_entry, None
        for sub in detail or [bar]:
            record_levels(sub)
            thresholds(sub, gap=True)
            if pending is not None:
                signal, intent = pending
                pending = None
                action = intent.action
                if action == "close":
                    if position:
                        close(sub.open, sub, "open", "signal", origin_signal=signal)
                        signal["status"] = "executed"
                    else:
                        signal["status"] = "ignored_flat"
                elif position and position["side"] == action:
                    signal["status"] = "ignored_same_side"
                else:
                    if position:
                        close(sub.open, sub, "open", "reversal", origin_signal=signal)
                    if cash <= 0:
                        signal["status"] = "ignored_nonpositive_equity"
                    else:
                        enter(intent, sub, sub.open, origin_signal=signal)
                        signal["status"] = "executed"
                event('signal_processed', sub.timestamp, signal_id=signal['signal_id'], status=signal['status'])
            if active_entry is not None:
                signal, order = active_entry
                d = 1 if order.intent.action == 'long' else -1
                gap_triggered = d*(sub.open-order.trigger_price) >= 0
                touched = (sub.high >= order.trigger_price) if d == 1 else (sub.low <= order.trigger_price)
                fill_price = sub.open if gap_triggered else order.trigger_price
                if position is not None:
                    signal['status'] = 'ignored_position'
                elif not touched:
                    signal['status'] = 'not_triggered'
                elif order.worst_price is not None and d*(fill_price-order.worst_price) > 0:
                    signal['status'] = 'ignored_price_cap'
                elif enter(order.intent, sub, fill_price, 'open' if gap_triggered else 'intrabar', signal):
                    signal['status'] = 'executed'
                else:
                    signal['status'] = 'ignored_nonpositive_equity'
                event('order_checked', sub.timestamp, signal_id=signal['signal_id'], status=signal['status'],
                      trigger_price=order.trigger_price, worst_price=order.worst_price,
                      resolution_ms=resolution_ms)
                if signal['status'] != 'not_triggered': active_entry = None
            record_levels(sub)
            thresholds(sub)
            if detail and intrabar_profit_protection:
                update_protection(sub)
            if execution_bars is not None:
                marked = equity(sub.close)
                if not isfinite(marked):
                    raise ValueError(f'账户数值溢出：{sub.timestamp}')
                execution_peak = max(execution_peak, marked)
                execution_points.append({'timestamp': sub.timestamp+resolution_ms, 'equity': marked, 'cash': cash,
                    'unrealized': marked-cash-(position['principal'] if position else 0),
                    'drawdown_pct': (execution_peak-marked)/execution_peak*100,
                    'resolution_ms': resolution_ms, 'fallback': fallback_time is not None})
        current = equity(bar.close)
        if not isfinite(current):
            raise ValueError(f"账户数值溢出：{bar.timestamp}")
        peak = max(peak, current)
        points.append({"timestamp": bar.timestamp + step_ms, "equity": current, "cash": cash,
                       "unrealized": current - cash - (position["principal"] if position else 0),
                       "drawdown_pct": (peak - current) / peak * 100})
        try:
            last_exit = MappingProxyType({k: trades[-1][k] for k in
                ('trade_id', 'side', 'entry_time', 'exit_time', 'exit_reason', 'return_pct')}) if trades else None
            intent = strategy.on_bar(Context(history, MappingProxyType(dict(position)) if position else None,
                                             cash, current, params, last_exit))
            entry_order = None
            if isinstance(intent, BarResult):
                observations.append(observation_record(intent, bar.timestamp))
                entry_order = intent.entry_order
                intent = intent.intent
            if intent is None:
                intent = Intent()
            if not isinstance(intent, Intent) or intent.action not in ("hold", "long", "short", "close"):
                raise ValueError("策略必须返回 Intent(long/short/close/hold)、BarResult 或 None")
            for name in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct"):
                value = getattr(intent, name)
                if value is not None and (isinstance(value, bool) or not isfinite(value) or not 0 < value < 100):
                        raise ValueError(f"{name} 必须介于 0 和 100 之间")
            distance = intent.stop_loss_distance
            if distance is not None:
                if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not isfinite(distance) or distance <= 0:
                    raise ValueError('stop_loss_distance 必须是有限正数')
                if intent.stop_loss_pct is not None:
                    raise ValueError('初始止损百分比与绝对距离不能同时设置')
            protection = intent.profit_protection
            if protection is not None:
                if not isinstance(protection, ProfitProtection):
                    raise ValueError("profit_protection 必须是 ProfitProtection")
                for name in ("activation_pct", "giveback_pct"):
                    value = getattr(protection, name)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 < value < 100:
                        raise ValueError(f"profit_protection.{name} 必须介于 0 和 100 之间")
            if entry_order is not None:
                validate_stop_entry(entry_order)
                if intent.action not in ('hold', 'close'):
                    raise ValueError('盘中入场委托不能和下一开盘入场同时发出')
        except Exception as exc:
            raise ValueError(f"策略 {getattr(strategy, '__file__', type(strategy).__name__)}，K 线 {bar.timestamp}: {exc}") from exc
        if intent.action != "hold":
            intent_fields = asdict(intent)
            # Preserve legacy record contents when the new feature is disabled.
            if intent.profit_protection is None:
                intent_fields.pop("profit_protection")
            if intent.stop_loss_distance is None:
                intent_fields.pop('stop_loss_distance')
            signal = {"timestamp": bar.timestamp, "decision_time": bar.timestamp + step_ms,
                      **intent_fields, "status": "pending", "signal_id": len(signals)+1}
            signals.append(signal)
            event('signal', signal['decision_time'], signal_id=signal['signal_id'], action=signal['action'], reason=intent.reason)
            pending = signal, intent
        if entry_order is not None:
            order_fields = asdict(entry_order.intent)
            signal = {'timestamp': bar.timestamp, 'decision_time': bar.timestamp+step_ms,
                      **order_fields, 'order_type': 'stop_entry', 'trigger_price': entry_order.trigger_price,
                      'worst_price': entry_order.worst_price, 'ambiguity_policy': entry_order.ambiguity_policy,
                      'status': 'pending', 'signal_id': len(signals)+1}
            signals.append(signal)
            event('stop_entry_order', signal['decision_time'], signal_id=signal['signal_id'], action=signal['action'],
                  trigger_price=entry_order.trigger_price, worst_price=entry_order.worst_price,
                  ambiguity_policy=entry_order.ambiguity_policy)
            pending_entry = signal, entry_order
        if not (detail and intrabar_profit_protection):
            resolution_ms = step_ms
            update_protection(bar)
        if progress and (i % 250 == 0 or i == len(bars) - 1):
            progress((i - warmup + 1) / (len(bars) - warmup))
    if pending:
        pending[0]["status"] = "unexecuted_end"
    if pending_entry:
        pending_entry[0]['status'] = 'unexecuted_end'
    if position:
        close(bars[-1].close, bars[-1], "close", "end_of_backtest")
        points[-1].update(cash=cash, unrealized=0.)
        if execution_points:
            execution_points[-1].update(cash=cash, unrealized=0.)
    wins = [t["profit"] for t in trades if t["profit"] > 0]
    losses = [-t["profit"] for t in trades if t["profit"] < 0]
    count = len(trades)
    report = {"initial_cash": initial_cash, "final_equity": cash, "profit": cash - initial_cash,
              "return_pct": (cash / initial_cash - 1) * 100,
              "max_drawdown_pct": max((p["drawdown_pct"] for p in points), default=0),
              "total_trades": count, "wins": len(wins), "losses": len(losses), "breakeven": count - len(wins) - len(losses),
              "win_rate": len(wins) / count * 100 if count else None,
              "average_return_pct": sum(t["return_pct"] for t in trades) / count if count else None,
              "payoff_ratio": (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if wins and losses else None,
              "profit_factor": sum(wins) / sum(losses) if losses else None,
              "average_duration_minutes": sum(t["duration_minutes"] for t in trades) / count if count else None,
              "ambiguous_trades": sum(t["ambiguous"] for t in trades),
              "notes": [DISCLAIMER, "最大回撤按每根收盘权益计算", "无亏损时利润因子为空；无交易时胜率为空", "K 线内退出的持仓时间按所属 K 线开盘时间近似"]}
    if any(s.get('order_type') == 'stop_entry' for s in signals):
        report['notes'].append('盘中突破委托仅用前一收盘已知价位；同根入场与止损先后不明的交易已标记，并按保存的 ambiguity_policy 处理')
    result = {"report": report, "trades": trades, "signals": signals, "fills": fills, "equity": points, "levels": levels,
              "events": events}
    if execution_bars is not None:
        result['execution_equity'] = execution_points
        report['execution_close_max_drawdown_pct'] = max((p['drawdown_pct'] for p in execution_points), default=0.)
        report['execution_drawdown_basis'] = 'mixed_closes' if fallback_candles else 'execution_closes'
        result['execution_detail'] = dict(detailed_candles=detailed_candles, fallback_candles=fallback_candles,
            profit_protection_update='execution_close' if intrabar_profit_protection else 'signal_close')
        report['notes'].append('交易信号保持原周期；匹配的细周期行情逐根成交。细周期缺失或不匹配时回退原周期，已计数。保护仅在选定周期收盘更新，下一根生效。')
    if observations:
        result["indicators"] = observations
    return result
