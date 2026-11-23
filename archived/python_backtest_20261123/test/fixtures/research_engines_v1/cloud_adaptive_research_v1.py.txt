"""Opt-in project engine copy: ATR-derived activation and causal ATR ratchet.
Legacy strategies remain unchanged. New lines become effective next candle only.
"""
from dataclasses import asdict
from math import isfinite,isclose
from types import MappingProxyType
from typing import Callable
from app.domain.local_backtest import (Bar,History,Context,Intent,BarResult,
    ProfitProtection,observation_record,DISCLAIMER)
from app.domain.cloud_adaptive_types_v1 import AdaptiveIntent,AdaptiveResult

def simulate(bars: list[Bar], strategy, parameters: dict, *, warmup: int,
             initial_cash: float = 10000, position_pct: float = 100,
             step_ms: int = 3600000, progress: Callable | None = None) -> dict:
    cash, peak = initial_cash, initial_cash
    position = None
    pending = None
    trades, signals, fills, points, levels = [], [], [], [], []
    observations = []
    past_bars = []
    history = History(past_bars)
    params = MappingProxyType(dict(parameters))

    def equity(price):
        if position is None:
            return cash
        return cash + position["principal"] + position["quantity"] * (price - position["entry_price"]) * position["direction"]

    def close(price, bar, phase, reason, ambiguous=False):
        nonlocal cash, position
        pnl = position["quantity"] * (price - position["entry_price"]) * position["direction"]
        cash += position["principal"] + pnl
        trades.append({**position, "exit_price": price, "exit_time": bar.timestamp,
                       "exit_phase": phase, "exit_reason": reason, "ambiguous": ambiguous,
                       "profit": pnl, "return_pct": pnl / position["principal"] * 100,
                       "duration_minutes": (bar.timestamp + (step_ms if phase == "close" else 0) - position["entry_time"]) / 60000})
        fills.append({"timestamp": bar.timestamp, "phase": phase, "action": "close", "price": price,
                      "quantity": position["quantity"], "trade_id": position["trade_id"], "reason": reason})
        position = None

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
        if stopped or gained:
            price = bar.open if gap else stop if stopped else target
            close(price, bar, "open" if gap else "intrabar",
                  position.get("stop_source", "stop_loss") if stopped else "take_profit", stopped and gained)

    for i, bar in enumerate(bars):
        past_bars.append(bar)
        if i < warmup:
            continue
        if not points:
            points.append({"timestamp": bar.timestamp, "equity": cash, "cash": cash, "unrealized": 0., "drawdown_pct": 0.})
        record_levels(bar)
        thresholds(bar, gap=True)
        if pending is not None:
            signal, intent = pending
            pending = None
            action = intent.action
            if action == "close":
                if position:
                    close(bar.open, bar, "open", "signal")
                    signal["status"] = "executed"
                else:
                    signal["status"] = "ignored_flat"
            elif position and position["side"] == action:
                signal["status"] = "ignored_same_side"
            else:
                if position:
                    close(bar.open, bar, "open", "reversal")
                if cash <= 0:
                    signal["status"] = "ignored_nonpositive_equity"
                else:
                    principal = cash * position_pct / 100
                    cash -= principal
                    d = 1 if action == "long" else -1
                    fixed = bar.open * (1 - d * intent.stop_loss_pct / 100) if intent.stop_loss_pct else None
                    if intent.stop_loss_distance is not None:
                        fixed = bar.open - d * intent.stop_loss_distance
                        if fixed <= 0:
                            raise ValueError('初始绝对距离止损价必须大于0')
                    trailing = bar.open * (1 - d * intent.trailing_stop_pct / 100) if intent.trailing_stop_pct else None
                    stops = [x for x in (fixed, trailing) if x is not None]
                    position = {"trade_id": len(trades) + 1, "side": action, "direction": d,
                                "entry_time": bar.timestamp, "entry_price": bar.open, "principal": principal,
                                "quantity": principal / bar.open, "stop": (max(stops) if d == 1 else min(stops)) if stops else None,
                                "target": bar.open * (1 + d * intent.take_profit_pct / 100) if intent.take_profit_pct else None,
                                "trailing_pct": intent.trailing_stop_pct, "best": bar.open}
                    if intent.profit_protection is not None:
                        pp=asdict(intent.profit_protection)
                        if isinstance(intent,AdaptiveIntent) and intent.activation_distance is not None:
                            pp['activation_pct']=100*intent.activation_distance/bar.open
                        position.update(profit_protection=pp,profit_peak_pct=0.,protection_active=False)
                    fills.append({"timestamp": bar.timestamp, "phase": "open", "action": action, "price": bar.open,
                                  "quantity": position["quantity"], "trade_id": position["trade_id"], "reason": intent.reason})
                    signal["status"] = "executed"
        record_levels(bar)
        thresholds(bar)
        current = equity(bar.close)
        if not isfinite(current):
            raise ValueError(f"账户数值溢出：{bar.timestamp}")
        peak = max(peak, current)
        points.append({"timestamp": bar.timestamp + step_ms, "equity": current, "cash": cash,
                       "unrealized": current - cash - (position["principal"] if position else 0),
                       "drawdown_pct": (peak - current) / peak * 100})
        try:
            intent = strategy.on_bar(Context(history, MappingProxyType(dict(position)) if position else None, cash, current, params))
            adaptive_distance=None
            if isinstance(intent, AdaptiveResult):
                adaptive_distance=intent.trailing_distance
                if adaptive_distance is not None and (not isfinite(adaptive_distance) or adaptive_distance<=0):
                    raise ValueError('跟踪距离必须是有限正数')
                if intent.record_observation:observations.append(observation_record(intent,bar.timestamp))
                intent=intent.intent
            elif isinstance(intent, BarResult):
                observations.append(observation_record(intent, bar.timestamp))
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
            if isinstance(intent,AdaptiveIntent) and intent.activation_distance is not None:
                if not isfinite(intent.activation_distance) or intent.activation_distance<=0:
                    raise ValueError('保护启动距离必须是有限正数')
            protection = intent.profit_protection
            if protection is not None:
                if not isinstance(protection, ProfitProtection):
                    raise ValueError("profit_protection 必须是 ProfitProtection")
                for name in ("activation_pct", "giveback_pct"):
                    value = getattr(protection, name)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 < value < 100:
                        raise ValueError(f"profit_protection.{name} 必须介于 0 和 100 之间")
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
                      **intent_fields, "status": "pending"}
            signals.append(signal)
            pending = signal, intent
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
                if adaptive_distance is not None:
                    # Use the just-closed candle's ATR and known favourable peak.
                    # Ratchet never loosens; activation cannot set a loss-side line.
                    updated=entry+d*max(0.,peak_profit-adaptive_distance)
                if position["stop"] is None or d*(updated-position["stop"]) > 0:
                    position["stop"] = updated
                    position["stop_source"] = "profit_protection"
        if progress and (i % 250 == 0 or i == len(bars) - 1):
            progress((i - warmup + 1) / (len(bars) - warmup))
    if pending:
        pending[0]["status"] = "unexecuted_end"
    if position:
        close(bars[-1].close, bars[-1], "close", "end_of_backtest")
        points[-1].update(cash=cash, unrealized=0.)
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
    result = {"report": report, "trades": trades, "signals": signals, "fills": fills, "equity": points, "levels": levels}
    if observations:
        result["indicators"] = observations
    return result
