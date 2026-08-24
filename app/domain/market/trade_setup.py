from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.domain.market.trade_setup_rules import (
    build_rule_trade_plan,
    resolve_rule_side,
    rolling_high,
    rolling_low,
    strategy_profile,
    style_profile,
)


@dataclass(frozen=True)
class TradeSetupRequest:
    symbol: str
    timeframe: str
    account_size: float
    style: str
    strategy: str
    mode: str = "rules"


@dataclass(frozen=True)
class TradeSetup:
    side: str
    entry: float
    target: float
    stop: float
    risk_reward: float
    confidence: int
    risk_amount: float
    entry_time: int
    style: str
    strategy: str
    source: str


@dataclass(frozen=True)
class TradeSetupResult:
    symbol: str
    timeframe: str
    timestamp: str
    current_price: float | None
    setup: TradeSetup | None
    reason: str
    source: str
    status: Literal["ready", "waiting", "unavailable", "rejected"]
    error_code: str | None


class TradeSetupEngine:
    def build_rules(
        self,
        request: TradeSetupRequest,
        kline_data: list[list[float]],
        indicators: dict[str, Any],
    ) -> TradeSetupResult:
        if len(kline_data) < 30:
            return self._empty(request, "Not enough market history", error_code="kline_insufficient")

        current_price = float(kline_data[-1][4])
        atr = self._positive_float(indicators.get("atr"))
        ema = self._positive_float(indicators.get("ema"))
        rsi = self._positive_float(indicators.get("rsi"))
        macd = indicators.get("macd") or (None, None, None)
        macd_hist = self._positive_or_negative_float(macd[2] if isinstance(macd, tuple) else macd.get("histogram"))

        if current_price <= 0 or atr is None or ema is None or rsi is None or macd_hist is None:
            return self._empty(request, "Indicators are not ready", error_code="indicators_incomplete")

        side = self._resolve_side(current_price=current_price, ema=ema, rsi=rsi, macd_hist=macd_hist)
        if not side:
            return self._empty(request, "No clear directional signal", error_code="no_clear_signal")

        support_price = rolling_low(kline_data, 20)
        resistance_price = rolling_high(kline_data, 20)
        plan = build_rule_trade_plan(
            side=side,
            entry_price=current_price,
            atr=atr,
            support_price=support_price,
            resistance_price=resistance_price,
            style=request.style,
            strategy=request.strategy,
        )

        risk_amount = max(request.account_size, 0) * style_profile(request.style)["risk_pct"]
        setup = TradeSetup(
            side=side,
            entry=plan["entry"],
            target=plan["target"],
            stop=plan["stop"],
            risk_reward=plan["risk_reward"],
            confidence=self._confidence(current_price=current_price, ema=ema, rsi=rsi, macd_hist=macd_hist, side=side),
            risk_amount=risk_amount,
            entry_time=int(kline_data[-1][0]),
            style=request.style,
            strategy=request.strategy,
            source="rules",
        )
        return TradeSetupResult(
            symbol=request.symbol,
            timeframe=request.timeframe,
            timestamp=datetime.now(timezone.utc).isoformat(),
            current_price=current_price,
            setup=setup,
            reason=self._reason(side=side, current_price=current_price, ema=ema, rsi=rsi, macd_hist=macd_hist),
            source="rules",
            status="ready",
            error_code=None,
        )

    def build_ai(
        self,
        request: TradeSetupRequest,
        kline_data: list[list[float]],
        ai_payload: dict[str, Any] | None,
        model_error_code: str | None = None,
    ) -> TradeSetupResult:
        if not ai_payload:
            return self._empty(
                request,
                "AI service is unavailable",
                source="ai",
                status="unavailable",
                error_code=model_error_code or "model_output_unavailable",
            )
        if not kline_data:
            return self._empty(
                request,
                "Not enough market history",
                source="ai",
                error_code="kline_insufficient",
            )

        current_price = float(kline_data[-1][4])
        side = self._normalize_side(ai_payload.get("side") or ai_payload.get("signal"))
        if not side:
            return self._empty(
                request,
                str(ai_payload.get("reason") or "The model recommends waiting"),
                source="ai",
                error_code="model_hold",
            )

        entry = self._positive_float(ai_payload.get("entry"))
        target = self._positive_float(ai_payload.get("target"))
        stop = self._positive_float(ai_payload.get("stop"))
        if entry is None or target is None or stop is None:
            return self._empty(
                request,
                "The model did not provide a complete plan",
                source="ai",
                status="rejected",
                error_code="model_plan_incomplete",
            )
        if not self._levels_match_side(side=side, entry=entry, target=target, stop=stop):
            return self._empty(
                request,
                "The model returned an invalid price structure",
                source="ai",
                status="rejected",
                error_code="model_price_structure_invalid",
            )

        risk_reward = abs(target - entry) / abs(entry - stop)
        setup = TradeSetup(
            side=side,
            entry=entry,
            target=target,
            stop=stop,
            risk_reward=risk_reward,
            confidence=self._clamp_int(ai_payload.get("confidence"), minimum=0, maximum=100, default=50),
            risk_amount=max(request.account_size, 0) * self._style_profile(request.style)["risk_pct"],
            entry_time=int(kline_data[-1][0]),
            style=request.style,
            strategy=request.strategy,
            source="ai",
        )
        return TradeSetupResult(
            symbol=request.symbol,
            timeframe=request.timeframe,
            timestamp=datetime.now(timezone.utc).isoformat(),
            current_price=current_price,
            setup=setup,
            reason=str(ai_payload.get("reason") or ai_payload.get("reasoning") or "The model generated a trade plan"),
            source="ai",
            status="ready",
            error_code=None,
        )

    def _resolve_side(self, *, current_price: float, ema: float, rsi: float, macd_hist: float) -> str | None:
        return resolve_rule_side(current_price=current_price, ema=ema, rsi=rsi, macd_hist=macd_hist)

    def _confidence(self, *, current_price: float, ema: float, rsi: float, macd_hist: float, side: str) -> int:
        score = 55
        if side == "long" and current_price > ema:
            score += 12
        if side == "short" and current_price < ema:
            score += 12
        if abs(macd_hist) > 0:
            score += 8
        if 45 <= rsi <= 65:
            score += 10
        return min(score, 88)

    def _reason(self, *, side: str, current_price: float, ema: float, rsi: float, macd_hist: float) -> str:
        direction = "做多" if side == "long" else "做空"
        ema_state = "站上" if current_price > ema else "跌破"
        macd_state = "偏强" if macd_hist >= 0 else "偏弱"
        return f"{direction}：价格{ema_state}EMA，MACD {macd_state}，RSI {rsi:.1f}"

    def _empty(
        self,
        request: TradeSetupRequest,
        reason: str,
        *,
        source: str | None = None,
        status: Literal["waiting", "unavailable", "rejected"] = "waiting",
        error_code: str,
    ) -> TradeSetupResult:
        return TradeSetupResult(
            symbol=request.symbol,
            timeframe=request.timeframe,
            timestamp=datetime.now(timezone.utc).isoformat(),
            current_price=None,
            setup=None,
            reason=reason,
            source=source or request.mode,
            status=status,
            error_code=error_code,
        )

    def _style_profile(self, style: str) -> dict[str, float]:
        return style_profile(style)

    def _strategy_profile(self, strategy: str) -> dict[str, float]:
        return strategy_profile(strategy)

    def _normalize_side(self, value: Any) -> str | None:
        text = str(value or "").strip().lower()
        if text in {"long", "buy", "做多", "多"}:
            return "long"
        if text in {"short", "sell", "做空", "空"}:
            return "short"
        return None

    def _levels_match_side(self, *, side: str, entry: float, target: float, stop: float) -> bool:
        if entry <= 0 or target <= 0 or stop <= 0 or entry == stop:
            return False
        if side == "long":
            return stop < entry < target
        return target < entry < stop

    def _clamp_int(self, value: Any, *, minimum: int, maximum: int, default: int) -> int:
        try:
            result = int(float(value))
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, result))

    def _positive_float(self, value: Any) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None

    def _positive_or_negative_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
