"""Public, causal strategy API and deterministic single-instrument simulator."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, asdict, field
from math import isfinite, isclose
from types import MappingProxyType
from typing import Any, Callable

ENGINE_VERSION = "5"
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
class BarResult:
    """Optional per-close observations. Recorded even without a trade signal."""
    intent: Intent | None = None
    values: dict[str, float | None] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    cloud: TrendCloud | None = None


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
                        position.update(profit_protection=asdict(intent.profit_protection),
                                        profit_peak_pct=0., protection_active=False)
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
            if isinstance(intent, BarResult):
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
