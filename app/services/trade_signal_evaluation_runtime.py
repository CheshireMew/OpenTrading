from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any

from app.application.persistence_ports import TradeSignalRepositoryPort
from app.contracts.research import TradeSignalEvaluationRunResponse
from app.infra.executor import run_database
from config import settings
from utils.logger import logger
from app.services.periodic_task import PeriodicTask
from app.domain.market.candles import candle_end_ms


class TradeSignalEvaluationRuntime:
    _HORIZONS_MS = {
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
        "24h": 24 * 60 * 60 * 1000,
        "7d": 7 * 24 * 60 * 60 * 1000,
    }

    def __init__(self, *, repository: TradeSignalRepositoryPort, market_query_service) -> None:
        self._repository = repository
        self._market_query = market_query_service
        self._lock = asyncio.Lock()
        self._periodic = PeriodicTask(
            "trade-signal-evaluation-runtime",
            lambda: self.evaluate_once(force=False),
            lambda: max(float(settings.TRADE_SIGNAL_EVALUATION_INTERVAL_SECONDS), 30.0),
        )

    async def start(self) -> None:
        await self._periodic.start()

    async def shutdown(self) -> None:
        await self._periodic.shutdown()

    async def evaluate_once(
        self,
        *,
        signal_id: str | None = None,
        force: bool = True,
    ) -> TradeSignalEvaluationRunResponse:
        async with self._lock:
            evaluated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            candidates = await run_database(lambda: self._repository.list_evaluation_candidates(signal_id))
            evaluated = 0
            resolved = 0
            unavailable = 0
            for signal in candidates:
                if not force and signal["outcomeStatus"] not in {"pending", "unavailable"}:
                    continue
                try:
                    payload = await self._evaluate_signal(signal, evaluated_at)
                    await run_database(
                        lambda signal_id=signal["id"], payload=payload: self._repository.record_evaluation(
                            signal_id,
                            payload,
                        )
                    )
                    evaluated += 1
                    if payload["outcomeStatus"] in {"target_hit", "stop_hit", "ambiguous", "expired"}:
                        resolved += 1
                    if payload["outcomeStatus"] == "unavailable":
                        unavailable += 1
                except Exception as exc:
                    unavailable += 1
                    logger.warning("Trade signal evaluation failed for %s: %s", signal.get("id"), exc)
            return TradeSignalEvaluationRunResponse(
                evaluatedAt=evaluated_at,
                candidateCount=len(candidates),
                evaluatedCount=evaluated,
                resolvedCount=resolved,
                unavailableCount=unavailable,
            )

    async def _evaluate_signal(
        self,
        signal: dict[str, Any],
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        entry = self._number(signal.get("entry"))
        target = self._number(signal.get("target"))
        stop = self._number(signal.get("stop"))
        entry_time = int(signal.get("entryTime") or 0)
        side = signal.get("side")
        if not entry or not target or not stop or entry_time <= 0 or side not in {"long", "short"}:
            return self._unavailable(evaluated_at)

        start_date = datetime.fromtimestamp(entry_time / 1000, tz=timezone.utc).date().isoformat()
        now_ms = int((evaluated_at if evaluated_at.tzinfo else evaluated_at.replace(tzinfo=timezone.utc)).timestamp() * 1000)
        expires_at = signal.get("expiresAt")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        expiry_ms = int(expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if expires_at and expires_at.tzinfo is None else int(expires_at.timestamp() * 1000) if expires_at else None
        cutoff = min(now_ms, expiry_ms) if expiry_ms is not None else now_ms
        if cutoff <= entry_time:
            return self._unavailable(evaluated_at)
        response = await self._market_query.get_full_history(
            symbol=signal["symbol"],
            timeframe=signal["timeframe"],
            start_date=start_date,
            end_date=datetime.fromtimestamp(cutoff / 1000, timezone.utc).date().isoformat(),
            fetch_policy="hydrate",
        )
        candles = sorted((item for item in response.items if item.timestamp >= entry_time
                          and candle_end_ms(item.timestamp, signal["timeframe"]) <= cutoff), key=lambda item: item.timestamp)
        if not candles:
            return self._unavailable(evaluated_at)
        coverage = response.coverage
        if not coverage.complete and not coverage.missing_ranges:
            return self._unavailable(evaluated_at)
        def covered_until(end):
            return not any(gap.start_ts < end and gap.end_ts > entry_time for gap in coverage.missing_ranges)

        target_hit_at = None
        stop_hit_at = None
        outcome = "pending"
        outcome_price = float(candles[-1].close)
        observed = []
        expected = entry_time
        for candle in candles:
            end = candle_end_ms(candle.timestamp, signal["timeframe"])
            if candle.timestamp != expected or not covered_until(end):
                return self._unavailable(evaluated_at)
            expected = end
            observed.append(candle)
            if side == "long":
                hit_target = candle.high >= target
                hit_stop = candle.low <= stop
            else:
                hit_target = candle.low <= target
                hit_stop = candle.high >= stop
            hit_time = datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc).replace(tzinfo=None)
            if hit_target and hit_stop:
                target_hit_at = hit_time
                stop_hit_at = hit_time
                outcome = "ambiguous"
                outcome_price = float(candle.close)
                break
            if hit_target:
                target_hit_at = hit_time
                outcome = "target_hit"
                outcome_price = target
                break
            if hit_stop:
                stop_hit_at = hit_time
                outcome = "stop_hit"
                outcome_price = stop
                break

        if outcome == "pending":
            # A missing completed bar, or an expiry inside an unresolved bar,
            # cannot prove that no target/stop was reached.
            if candle_end_ms(expected, signal["timeframe"]) <= cutoff or not covered_until(expected):
                return self._unavailable(evaluated_at)
            if expiry_ms is not None and now_ms >= expiry_ms:
                if expected != expiry_ms:
                    return self._unavailable(evaluated_at)
                outcome = "expired"

        highs = [float(item.high) for item in observed]
        lows = [float(item.low) for item in observed]
        if side == "long":
            mfe_pct = (max(highs) / entry - 1) * 100
            mae_pct = (min(lows) / entry - 1) * 100
        else:
            mfe_pct = (1 - min(lows) / entry) * 100
            mae_pct = (1 - max(highs) / entry) * 100

        forward_returns: dict[str, float | None] = {}
        for name, horizon in self._HORIZONS_MS.items():
            horizon_end = entry_time + horizon
            prefix = [item for item in candles if candle_end_ms(item.timestamp, signal["timeframe"]) <= horizon_end]
            contiguous = bool(prefix) and prefix[0].timestamp == entry_time and all(
                right.timestamp == candle_end_ms(left.timestamp, signal["timeframe"]) for left, right in zip(prefix, prefix[1:]))
            point = prefix[-1] if contiguous and candle_end_ms(prefix[-1].timestamp, signal["timeframe"]) == horizon_end and covered_until(horizon_end) else None
            forward_returns[name] = round((float(point.close) / entry - 1) * (1 if side == "long" else -1) * 100, 6) if point is not None else None
        return {
            "outcomeStatus": outcome,
            "outcomePrice": outcome_price,
            "targetHitAt": target_hit_at,
            "stopHitAt": stop_hit_at,
            "mfePct": round(mfe_pct, 6),
            "maePct": round(mae_pct, 6),
            "forwardReturns": forward_returns,
            "evaluatedAt": evaluated_at,
        }

    @staticmethod
    def _unavailable(evaluated_at: datetime) -> dict[str, Any]:
        return {
            "outcomeStatus": "unavailable",
            "outcomePrice": None,
            "targetHitAt": None,
            "stopHitAt": None,
            "mfePct": None,
            "maePct": None,
            "forwardReturns": {},
            "evaluatedAt": evaluated_at,
        }

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) and parsed > 0 else None
