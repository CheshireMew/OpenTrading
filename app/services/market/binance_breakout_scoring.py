from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BreakoutScore:
    natural: int
    momentum: int
    reasons: list[str]


def score_breakout_candidate(
    item: dict[str, Any],
    snapshot_15m: dict[str, float | None],
    snapshot_1h: dict[str, float | None],
) -> BreakoutScore:
    natural_score = 0
    momentum_score = 0
    reasons: list[str] = []
    pullback_from_high_pct = snapshot_15m.get("pullback_from_high_pct")
    if pullback_from_high_pct is not None:
        if pullback_from_high_pct >= -2.5:
            natural_score += 30
            reasons.append("离高点不远，回撤不深")
        elif pullback_from_high_pct >= -5.0:
            natural_score += 16
    range_position_pct = snapshot_15m.get("range_position_pct")
    if range_position_pct is not None:
        if range_position_pct >= 70.0:
            natural_score += 24
            reasons.append("价格仍压在强势区间上沿")
        elif range_position_pct >= 55.0:
            natural_score += 12
    green_ratio_pct = snapshot_15m.get("green_ratio_pct")
    if green_ratio_pct is not None:
        if 45.0 <= green_ratio_pct <= 82.0:
            natural_score += 20
            reasons.append("短线节奏均匀，不是单根硬拉")
        elif 35.0 <= green_ratio_pct <= 90.0:
            natural_score += 10
    max_bar_change_pct = snapshot_15m.get("max_bar_change_pct")
    spike_limit = min(8.0, max(3.0, (item.get("price_change_pct") or 0.0) * 0.45))
    if max_bar_change_pct is not None:
        if max_bar_change_pct <= spike_limit:
            natural_score += 26
        elif max_bar_change_pct <= spike_limit * 1.5:
            natural_score += 10
    ema20_gap_15m = snapshot_15m.get("ema20_gap_pct")
    ema20_gap_1h = snapshot_1h.get("ema20_gap_pct")
    if ema20_gap_15m is not None and ema20_gap_15m > 0:
        momentum_score += 20
        reasons.append("15 分钟仍站在均线之上")
    if ema20_gap_1h is not None and ema20_gap_1h > 0:
        momentum_score += 20
        reasons.append("1 小时趋势还没掉头")
    rsi_15m = snapshot_15m.get("rsi")
    if rsi_15m is not None:
        if 55.0 <= rsi_15m <= 78.0:
            momentum_score += 15
        elif 50.0 <= rsi_15m <= 82.0:
            momentum_score += 8
    rsi_1h = snapshot_1h.get("rsi")
    if rsi_1h is not None:
        if 55.0 <= rsi_1h <= 75.0:
            momentum_score += 15
        elif 50.0 <= rsi_1h <= 80.0:
            momentum_score += 8
    macd_hist_15m = snapshot_15m.get("macd_hist")
    if macd_hist_15m is not None and macd_hist_15m > 0:
        momentum_score += 15
    change_15m_pct = snapshot_15m.get("bar_change_pct")
    if change_15m_pct is not None and change_15m_pct > 0:
        momentum_score += 8
    change_1h_pct = snapshot_1h.get("bar_change_pct")
    if change_1h_pct is not None and change_1h_pct > 0:
        momentum_score += 14
        reasons.append("最近 1 小时还在续涨")
    if pullback_from_high_pct is not None and pullback_from_high_pct >= -1.5:
        momentum_score += 8
    return BreakoutScore(
        natural=min(int(round(natural_score)), 100),
        momentum=min(int(round(momentum_score)), 100),
        reasons=list(dict.fromkeys(reasons)),
    )


def resolve_follow_status(
    snapshot_15m: dict[str, float | None],
    snapshot_1h: dict[str, float | None],
) -> str:
    change_15m_pct = snapshot_15m.get("bar_change_pct")
    change_1h_pct = snapshot_1h.get("bar_change_pct")
    pullback_from_high_pct = snapshot_15m.get("pullback_from_high_pct")
    range_position_pct = snapshot_15m.get("range_position_pct")
    if (
        change_15m_pct is not None and change_15m_pct > 0
        and pullback_from_high_pct is not None and pullback_from_high_pct >= -1.5
        and range_position_pct is not None and range_position_pct >= 85.0
    ):
        return "继续上行"
    if (
        change_1h_pct is not None and change_1h_pct >= 0
        and pullback_from_high_pct is not None and pullback_from_high_pct >= -3.5
        and range_position_pct is not None and range_position_pct >= 65.0
    ):
        return "高位蓄势"
    return "冲高回撤"


def resolve_verdict(*, structure_ok: bool, momentum_ok: bool, follow_status: str) -> str:
    if structure_ok and momentum_ok and follow_status in {"继续上行", "高位蓄势"}:
        return "优先关注"
    if structure_ok or momentum_ok:
        return "继续跟踪"
    return "只做观察"
