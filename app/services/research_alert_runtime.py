from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any

from app.application.persistence_ports import ResearchAlertEvaluationPort
from app.contracts.research import ResearchAlertEvaluationResponse
from app.infra.executor import run_database
from config import settings
from utils.logger import logger
from app.services.periodic_task import PeriodicTask
from app.domain.research_alerts import should_trigger
from app.services.market.binance_market_observations import BinanceMarketObservations


class ResearchAlertRuntime:
    def __init__(
        self,
        *,
        research_repository: ResearchAlertEvaluationPort,
        market_query_service,
        binance_market_service,
    ) -> None:
        self._research_repository = research_repository
        self._market_query = market_query_service
        self._binance_market = binance_market_service
        self._evaluation_lock = asyncio.Lock()
        self._chart_prices = None
        self._periodic = PeriodicTask(
            "research-alert-runtime",
            self.evaluate_once,
            lambda: max(float(settings.RESEARCH_ALERT_INTERVAL_SECONDS), 10.0),
        )

    async def start(self, chart_market=None) -> None:
        if chart_market is not None and self._chart_prices is None:
            from app.services.chart_price_alert_runtime import ChartPriceAlertRuntime
            self._chart_prices = ChartPriceAlertRuntime(self._research_repository, chart_market)
            await self._chart_prices.start()
        await self._periodic.start()

    async def shutdown(self) -> None:
        await self._periodic.shutdown()
        if self._chart_prices is not None:
            await self._chart_prices.shutdown()
            self._chart_prices = None

    async def evaluate_once(self) -> ResearchAlertEvaluationResponse:
        async with self._evaluation_lock:
            evaluated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            rules = await run_database(self._research_repository.list_enabled_alerts)
            rules = [rule for rule in rules if not rule.get("configuration", {}).get("chartSymbolId")
                     and rule["metric"] != "portfolio_drift_pct"]
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

            observations = BinanceMarketObservations(snapshot, market_page)
            evaluated_count = 0
            triggered_count = 0
            unavailable_count = 0
            for rule in rules:
                try:
                    value = await self._resolve_value(
                        rule,
                        snapshot=snapshot,
                        market_page=market_page,
                        observations=observations,
                    )
                    if value is None or not math.isfinite(value):
                        unavailable_count += 1
                        continue
                    saved = await run_database(
                        lambda rule=rule, value=value: (
                            self._research_repository.record_alert_evaluation(
                                rule["id"],
                                value=value,
                                evaluated_at=evaluated_at,
                                expected_version=rule["version"],
                            )
                        )
                    )
                    if saved is None:
                        unavailable_count += 1
                        continue
                    evaluated_count += 1
                    if saved["lastTriggeredAt"] == evaluated_at:
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

    async def _resolve_value(self, rule: dict[str, Any], *, snapshot, market_page, observations=None) -> float | None:
        projection = observations or BinanceMarketObservations(snapshot, market_page)
        metrics = projection.metrics(rule["symbol"])
        metric = rule["metric"]
        if metric == "breakout_score":
            kind = str((rule.get("configuration") or {}).get("scoreKind") or "max")
            metric = kind if kind in {"natural", "momentum"} else metric
        value = metrics.get(metric)
        if value is None and metric == "price":
            response = await self._market_query.get_current_price(symbol=rule["symbol"], timeframe="1h")
            return self._float(response.current_price)
        return value

    @staticmethod
    def _should_trigger(rule: dict[str, Any], value: float, evaluated_at: datetime) -> bool:
        return should_trigger(rule, value, evaluated_at)

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None
