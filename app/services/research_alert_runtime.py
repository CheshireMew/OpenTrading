from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from app.application.persistence_ports import PortfolioRepositoryPort, ResearchRepositoryPort
from app.contracts.research import ResearchAlertEvaluationResponse
from app.infra.executor import run_database
from config import settings
from utils.logger import logger


class ResearchAlertRuntime:
    def __init__(
        self,
        *,
        research_repository: ResearchRepositoryPort,
        market_query_service,
        binance_market_service,
        portfolio_repository: PortfolioRepositoryPort,
    ) -> None:
        self._research_repository = research_repository
        self._market_query = market_query_service
        self._binance_market = binance_market_service
        self._portfolio_repository = portfolio_repository
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._evaluation_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="research-alert-runtime")

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

    async def evaluate_once(self) -> ResearchAlertEvaluationResponse:
        async with self._evaluation_lock:
            evaluated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            rules = await run_database(self._research_repository.list_enabled_alerts)
            if not rules:
                return ResearchAlertEvaluationResponse(
                    evaluatedAt=evaluated_at,
                    ruleCount=0,
                    evaluatedCount=0,
                    triggeredCount=0,
                    unavailableCount=0,
                )

            snapshot = await self._binance_market.snapshot_service.get_market_page_snapshot_data()
            needs_market_page = any(rule["metric"] in {"breakout_score", "oi_change_1h_pct"} for rule in rules)
            market_page = (
                await self._binance_market.page.get_page(min_rise_pct=0, limit=100, quote_asset="USDT")
                if needs_market_page
                else None
            )
            needs_portfolios = any(rule["metric"] == "portfolio_drift_pct" for rule in rules)
            portfolios = await run_database(self._portfolio_repository.get_collection) if needs_portfolios else None

            evaluated_count = 0
            triggered_count = 0
            unavailable_count = 0
            for rule in rules:
                try:
                    value = await self._resolve_value(
                        rule,
                        snapshot=snapshot,
                        market_page=market_page,
                        portfolios=portfolios,
                    )
                    if value is None or not math.isfinite(value):
                        unavailable_count += 1
                        continue
                    triggered = self._should_trigger(rule, value, evaluated_at)
                    await run_database(
                        lambda rule=rule, value=value, triggered=triggered: (
                            self._research_repository.record_alert_evaluation(
                                rule["id"],
                                value=value,
                                evaluated_at=evaluated_at,
                                triggered=triggered,
                            )
                        )
                    )
                    evaluated_count += 1
                    if triggered:
                        triggered_count += 1
                except Exception as exc:
                    unavailable_count += 1
                    logger.warning("Research alert evaluation failed for %s: %s", rule.get("id"), exc)

            return ResearchAlertEvaluationResponse(
                evaluatedAt=evaluated_at,
                ruleCount=len(rules),
                evaluatedCount=evaluated_count,
                triggeredCount=triggered_count,
                unavailableCount=unavailable_count,
            )

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.evaluate_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Research alert evaluation cycle failed")
            event = self._stop_event
            if event is None:
                return
            try:
                await asyncio.wait_for(
                    event.wait(),
                    timeout=max(float(settings.RESEARCH_ALERT_INTERVAL_SECONDS), 10.0),
                )
                return
            except asyncio.TimeoutError:
                continue

    async def _resolve_value(self, rule: dict[str, Any], *, snapshot, market_page, portfolios) -> float | None:
        metric = rule["metric"]
        symbol = self._ticker_symbol(rule["symbol"])
        spot_tickers = self._rows_by_symbol(snapshot.get("spot_ticker", {}).get("items", []))
        usdm_tickers = self._rows_by_symbol(snapshot.get("usdm_ticker", {}).get("items", []))
        marks = self._rows_by_symbol(snapshot.get("usdm_mark", {}).get("items", []))

        if metric == "price":
            row = spot_tickers.get(symbol) or marks.get(symbol) or usdm_tickers.get(symbol)
            value = self._float((row or {}).get("last_price") or (row or {}).get("mark_price"))
            if value is not None:
                return value
            response = await self._market_query.get_current_price(symbol=rule["symbol"], timeframe="1h")
            return self._float(response.current_price)
        if metric == "price_change_24h":
            row = spot_tickers.get(symbol) or usdm_tickers.get(symbol)
            return self._float((row or {}).get("price_change_pct"))
        if metric == "funding_rate_pct":
            value = self._float((marks.get(symbol) or {}).get("funding_rate_pct"))
            if value is not None:
                return value
            return self._float((marks.get(symbol) or {}).get("last_funding_rate"))
        if metric == "breakout_score" and market_page is not None:
            item = next((row for row in market_page.monitor.items if self._ticker_symbol(row.symbol) == symbol), None)
            if item is None:
                return None
            score_kind = str((rule.get("configuration") or {}).get("scoreKind") or "max")
            if score_kind == "natural":
                return float(item.natural_score)
            if score_kind == "momentum":
                return float(item.momentum_score)
            return float(max(item.natural_score, item.momentum_score))
        if metric == "oi_change_1h_pct" and market_page is not None:
            for board in market_page.contract_boards.values():
                item = next((row for row in board.items if self._ticker_symbol(row.symbol or "") == symbol), None)
                if item is not None:
                    return self._float(item.oi_change_1h_pct)
            return None
        if metric == "portfolio_drift_pct" and portfolios is not None:
            return self._portfolio_drift(rule, portfolios)
        if metric == "rsi":
            timeframe = str((rule.get("configuration") or {}).get("timeframe") or "1h")
            response = await self._market_query.get_realtime(
                symbol=rule["symbol"],
                timeframe=timeframe,
                limit=200,
            )
            return self._float(response.indicators.rsi)
        return None

    @classmethod
    def _portfolio_drift(cls, rule: dict[str, Any], collection) -> float | None:
        configuration = rule.get("configuration") or {}
        portfolio_id = str(configuration.get("portfolioId") or collection.active_portfolio_id or "")
        payload = next(
            (item for item in collection.active_payloads if str(item.get("id")) == portfolio_id),
            None,
        )
        if not payload:
            return None
        assets = list(payload.get("assets") or [])
        target_total = sum(max(cls._float(asset.get("targetWeight")) or 0.0, 0.0) for asset in assets)
        current_values = [
            max((cls._float(asset.get("units")) or 0.0) * (cls._float(asset.get("currentPrice")) or 0.0), 0.0)
            for asset in assets
        ]
        current_total = sum(current_values)
        if target_total <= 0 or current_total <= 0:
            return None
        normalized_symbol = str(rule["symbol"]).upper()
        for asset, current_value in zip(assets, current_values):
            if str(asset.get("symbol") or "").upper() != normalized_symbol:
                continue
            target = max(cls._float(asset.get("targetWeight")) or 0.0, 0.0) / target_total * 100
            current = current_value / current_total * 100
            drift = current - target
            return drift if configuration.get("signed") else abs(drift)
        return None

    @staticmethod
    def _should_trigger(rule: dict[str, Any], value: float, evaluated_at: datetime) -> bool:
        operator = rule["operator"]
        threshold = float(rule["threshold"])
        secondary = rule.get("secondary_threshold")
        last_value = rule.get("last_value")
        condition = False
        if operator == "gt":
            condition = value > threshold
        elif operator == "gte":
            condition = value >= threshold
        elif operator == "lt":
            condition = value < threshold
        elif operator == "lte":
            condition = value <= threshold
        elif operator == "crosses_above":
            condition = last_value is not None and float(last_value) < threshold <= value
        elif operator == "crosses_below":
            condition = last_value is not None and float(last_value) > threshold >= value
        elif operator == "between" and secondary is not None:
            condition = threshold <= value <= float(secondary)
        elif operator == "outside" and secondary is not None:
            condition = value < threshold or value > float(secondary)
        if not condition:
            return False
        last_triggered = rule.get("last_triggered_at")
        cooldown = max(int(rule.get("cooldown_minutes") or 0), 0)
        return not (last_triggered is not None and evaluated_at < last_triggered + timedelta(minutes=cooldown))

    @staticmethod
    def _rows_by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(row.get("symbol") or "").upper(): row for row in rows if row.get("symbol")}

    @staticmethod
    def _ticker_symbol(symbol: str) -> str:
        return str(symbol or "").strip().upper().replace("/", "")

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None
