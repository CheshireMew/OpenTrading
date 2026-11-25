"""Keep chart price alerts subscribed even when their chart is not open."""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone

from app.domain.research_alerts import should_trigger
from app.infra.executor import run_database
from app.services.periodic_task import PeriodicTask
from utils.logger import logger


class ChartPriceAlertRuntime:
    def __init__(self, repository, market):
        self.repository, self.market = repository, market
        self.rules: dict[str, dict] = {}
        self.workers: dict[str, asyncio.Task] = {}
        self.periodic = PeriodicTask("chart-price-alerts", self.refresh, lambda: 2.0)

    async def start(self):
        await self.periodic.start()

    async def shutdown(self):
        await self.periodic.shutdown()
        workers, self.workers = list(self.workers.values()), {}
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    async def refresh(self):
        rules = await run_database(self.repository.list_enabled_alerts)
        self.rules = {rule["id"]: rule for rule in rules if rule.get("configuration", {}).get("chartSymbolId")}
        symbols = {rule["configuration"]["chartSymbolId"] for rule in self.rules.values()}
        stopped = []
        for symbol in list(self.workers):
            if symbol not in symbols or self.workers[symbol].done():
                task = self.workers.pop(symbol)
                task.cancel()
                stopped.append(task)
        await asyncio.gather(*stopped, return_exceptions=True)
        for symbol in symbols - self.workers.keys():
            self.workers[symbol] = asyncio.create_task(self.watch(symbol), name=f"chart-alert:{symbol}")

    async def watch(self, symbol):
        queue = asyncio.Queue(maxsize=100)
        timeframe = "1d" if symbol.startswith("index:") else "1m"
        self.market.subscribe(symbol, timeframe, queue)
        try:
            while True:
                message = await queue.get()
                if message.get("type") != "bar":
                    continue
                if symbol.startswith("index:"):
                    # The index feed replays its last two daily observations.
                    # Compare only the latest one with the stored alert baseline.
                    while not queue.empty():
                        latest = queue.get_nowait()
                        if latest.get("type") == "bar":
                            message = latest
                bar = message["bar"]
                # Initial/reconnect history is replayed by the shared market feed.
                # Only an explicitly live feed message is a crypto price observation.
                if not symbol.startswith("index:") and not message.get("live"):
                    continue
                try:
                    await self.evaluate_price(symbol, float(bar["close"]))
                except Exception:
                    logger.exception("Chart price alert evaluation failed for %s", symbol)
        finally:
            self.market.unsubscribe(symbol, timeframe, queue)

    async def evaluate_price(self, symbol: str, price: float):
        if not math.isfinite(price) or price <= 0:
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for rule in list(self.rules.values()):
            if rule["configuration"]["chartSymbolId"] != symbol:
                continue
            triggered = should_trigger(rule, price, now)
            if rule.get("last_value") == price and not triggered:
                continue
            saved = await run_database(lambda rule=rule: self.repository.record_alert_evaluation(
                rule["id"], value=price, evaluated_at=now, expected_version=rule["version"]))
            # Never overwrite a newer refresh snapshot after awaiting the database.
            if self.rules.get(rule["id"]) is rule:
                if saved is None or not saved["enabled"] or saved["archivedAt"]:
                    self.rules.pop(rule["id"], None)
                else:
                    rule["last_value"] = saved["lastValue"]
                    rule["last_triggered_at"] = saved["lastTriggeredAt"]
