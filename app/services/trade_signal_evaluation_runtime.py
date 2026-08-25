from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.application.persistence_ports import TradeSignalRepositoryPort
from app.contracts.research import TradeSignalEvaluationRunResponse
from app.infra.executor import run_database
from config import settings
from utils.logger import logger


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
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="trade-signal-evaluation-runtime")

    async def shutdown(self) -> None:
        event = self._stop_event
        self._stop_event = None
        if event is not None:
            event.set()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

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
        response = await self._market_query.get_full_history(
            symbol=signal["symbol"],
            timeframe=signal["timeframe"],
            start_date=start_date,
            fetch_policy="hydrate",
        )
        candles = [item for item in response.items if item.timestamp >= entry_time]
        if not candles:
            return self._unavailable(evaluated_at)

        target_hit_at = None
        stop_hit_at = None
        outcome = "pending"
        outcome_price = float(candles[-1].close)
        observed = []
        for candle in candles:
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

        expires_at = signal.get("expiresAt")
        if outcome == "pending" and expires_at is not None and evaluated_at >= expires_at:
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
            point = next((item for item in candles if item.timestamp >= entry_time + horizon), None)
            forward_returns[name] = round((float(point.close) / entry - 1) * 100, 6) if point is not None else None
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

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.evaluate_once(force=False)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Trade signal evaluation cycle failed")
            event = self._stop_event
            if event is None:
                return
            try:
                await asyncio.wait_for(
                    event.wait(),
                    timeout=max(float(settings.TRADE_SIGNAL_EVALUATION_INTERVAL_SECONDS), 30.0),
                )
                return
            except asyncio.TimeoutError:
                continue

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
