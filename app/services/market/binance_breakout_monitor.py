from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from config import settings

from .binance_breakout_candidates import collect_derivatives_candidates, collect_spot_candidates
from .binance_breakout_scoring import resolve_follow_status, resolve_verdict, score_breakout_candidate
from .binance_breakout_snapshot import build_breakout_snapshot


KlineLoader = Callable[[str, str, str, int], Awaitable[dict[str, Any]]]
ENRICH_CANDIDATE_TIMEOUT_SECONDS = 3.0


class BinanceBreakoutMonitor:
    def __init__(self, kline_loader: KlineLoader) -> None:
        self._kline_loader = kline_loader

    async def build(
        self,
        *,
        market_snapshot: dict[str, Any],
        min_rise_pct: float,
        limit: int,
        quote_asset: str,
    ) -> dict[str, Any]:
        spot_response = market_snapshot["spot_ticker"]
        usdm_ticker_response = market_snapshot["usdm_ticker"]
        usdm_mark_response = market_snapshot["usdm_mark"]
        candidates = [
            *collect_spot_candidates(
                spot_response.get("items", []),
                min_rise_pct=min_rise_pct,
                quote_asset=quote_asset,
            ),
            *collect_derivatives_candidates(
                "usdm",
                usdm_ticker_response.get("items", []),
                usdm_mark_response.get("items", []),
                min_rise_pct=min_rise_pct,
                quote_asset=quote_asset,
            ),
        ]
        ranked = sorted(
            candidates,
            key=lambda item: ((item.get("price_change_pct") or -999.0), (item.get("quote_volume") or 0.0)),
            reverse=True,
        )[:limit]
        semaphore = asyncio.Semaphore(max(int(settings.BINANCE_BREAKOUT_MAX_CONCURRENCY), 1))

        async def enrich(item: dict[str, Any]) -> None:
            async with semaphore:
                await self._enrich_candidate(item)

        await asyncio.gather(*(enrich(item) for item in ranked))
        ranked.sort(
            key=lambda item: (
                item.get("verdict") == "优先关注",
                item.get("momentum_score", 0),
                item.get("natural_score", 0),
                item.get("price_change_pct") or -999.0,
            ),
            reverse=True,
        )
        summary = self._summary(ranked)
        return {
            "exchange": "binance",
            "min_rise_pct": float(min_rise_pct),
            "quote_asset": quote_asset,
            "updated_at": int(time.time() * 1000),
            "summary": summary,
            "items": ranked,
        }

    def derive(self, monitor: dict[str, Any], *, min_rise_pct: float, limit: int) -> dict[str, Any]:
        items = [
            dict(item)
            for item in monitor.get("items", [])
            if float(item.get("price_change_pct") or 0.0) >= float(min_rise_pct)
        ][:limit]
        return {
            **monitor,
            "min_rise_pct": float(min_rise_pct),
            "summary": self._summary(items),
            "items": items,
        }

    @staticmethod
    def _summary(ranked: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "monitored_count": len(ranked),
            "natural_count": sum(1 for item in ranked if item.get("structure_ok")),
            "momentum_count": sum(1 for item in ranked if item.get("momentum_ok")),
            "focus_count": sum(1 for item in ranked if item.get("verdict") == "优先关注"),
            "advancing_count": sum(1 for item in ranked if item.get("follow_status") in {"继续上行", "高位蓄势"}),
            "spot_count": sum(1 for item in ranked if item.get("market") == "spot"),
            "contract_count": sum(1 for item in ranked if item.get("market") == "usdm"),
        }

    async def _enrich_candidate(self, item: dict[str, Any]) -> None:
        try:
            kline_15m, kline_1h = await asyncio.wait_for(
                asyncio.gather(
                    self._kline_loader(item["market"], item["symbol"], "15m", 80),
                    self._kline_loader(item["market"], item["symbol"], "1h", 80),
                ),
                timeout=ENRICH_CANDIDATE_TIMEOUT_SECONDS,
            )
        except Exception:
            item.setdefault("follow_status", "数据不足")
            item.setdefault("verdict", "只做观察")
            item.setdefault("reasons", ["短周期数据暂时不足"])
            return

        snapshot_15m = build_breakout_snapshot(kline_15m.get("items", []), recent_window=16, green_window=12, window_bars=4)
        snapshot_1h = build_breakout_snapshot(kline_1h.get("items", []), recent_window=12, green_window=8, window_bars=4)
        score = score_breakout_candidate(item, snapshot_15m, snapshot_1h)
        item["change_15m_pct"] = snapshot_15m.get("bar_change_pct")
        item["change_1h_pct"] = snapshot_1h.get("bar_change_pct")
        item["change_4h_pct"] = snapshot_1h.get("window_change_pct")
        item["pullback_from_high_pct"] = snapshot_15m.get("pullback_from_high_pct")
        item["range_position_pct"] = snapshot_15m.get("range_position_pct")
        item["ema20_gap_15m_pct"] = snapshot_15m.get("ema20_gap_pct")
        item["ema20_gap_1h_pct"] = snapshot_1h.get("ema20_gap_pct")
        item["rsi_15m"] = snapshot_15m.get("rsi")
        item["rsi_1h"] = snapshot_1h.get("rsi")
        item["macd_hist_15m"] = snapshot_15m.get("macd_hist")
        item["green_ratio_15m_pct"] = snapshot_15m.get("green_ratio_pct")
        item["natural_score"] = score.natural
        item["momentum_score"] = score.momentum
        item["structure_ok"] = score.natural >= 65
        item["momentum_ok"] = score.momentum >= 65
        item["follow_status"] = resolve_follow_status(snapshot_15m, snapshot_1h)
        item["verdict"] = resolve_verdict(
            structure_ok=item["structure_ok"],
            momentum_ok=item["momentum_ok"],
            follow_status=item["follow_status"],
        )
        item["reasons"] = score.reasons[:4]
