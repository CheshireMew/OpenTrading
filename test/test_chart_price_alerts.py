from datetime import timedelta
import asyncio

import pytest

from app.contracts.research import ResearchAlertCreateCommand, ResearchAlertUpdateCommand
from app.domain.research_alerts import should_trigger
from app.infra.persistence.research_repository import ResearchRepository
from app.services.research_service import ResearchService
from app.services.chart_price_alert_runtime import ChartPriceAlertRuntime
from utils.time import utc_now_naive


def create_alert(service, symbol="binance:usdm:BTCUSDT", **overrides):
    return service.create_alert(ResearchAlertCreateCommand(**{
        "symbol": "BTC/USDT", "name": "BTC price", "metric": "price", "operator": "crosses",
        "threshold": 100, "notificationChannels": ["in_app", "windows", "sound"],
        "configuration": {"chartSymbolId": symbol, "initialPrice": 90, "once": True}, **overrides,
    }))


@pytest.mark.asyncio
async def test_chart_alert_uses_venue_and_persists_one_shot(installed_database_runtime):
    repository = ResearchRepository(installed_database_runtime)
    service = ResearchService(repository)
    alert = create_alert(service)
    runtime = ChartPriceAlertRuntime(repository.alerts, None)
    runtime.rules = {row["id"]: row for row in repository.list_enabled_alerts()}
    await runtime.evaluate_price("binance:spot:BTCUSDT", 110)
    assert service.get_workbench(event_limit=10, note_limit=1).alerts[0].enabled
    await runtime.evaluate_price("binance:usdm:BTCUSDT", 105)
    await runtime.evaluate_price("binance:usdm:BTCUSDT", 110)
    # Even a stale worker cannot trigger the completed alert again.
    repository.record_alert_evaluation(alert.id, value=120, evaluated_at=utc_now_naive(), triggered=True)
    result = service.get_workbench(event_limit=10, note_limit=1)
    events = [event for event in result.events if event.kind == "alert_triggered"]
    assert len(events) == 1
    assert events[0].payload["chartSymbolId"] == "binance:usdm:BTCUSDT"
    assert events[0].payload["notificationChannels"] == ["in_app", "windows", "sound"]
    assert result.alerts[0].enabled is False
    assert result.alerts[0].version > alert.version


def test_chart_alert_rechecks_an_edited_or_paused_rule(installed_database_runtime):
    repository = ResearchRepository(installed_database_runtime)
    service = ResearchService(repository)
    alert = create_alert(service)
    updated = service.update_alert(alert.id, ResearchAlertUpdateCommand(**{
        **alert.model_dump(include=set(ResearchAlertCreateCommand.model_fields)),
        "threshold": 200, "expectedVersion": alert.version,
    }))
    repository.record_alert_evaluation(alert.id, value=110, evaluated_at=utc_now_naive(), triggered=True)
    paused = service.update_alert(alert.id, ResearchAlertUpdateCommand(**{
        **updated.model_dump(include=set(ResearchAlertCreateCommand.model_fields)),
        "enabled": False, "expectedVersion": updated.version,
    }))
    repository.record_alert_evaluation(alert.id, value=250, evaluated_at=utc_now_naive(), triggered=True)
    result = service.get_workbench(event_limit=10, note_limit=1)
    assert not [event for event in result.events if event.kind == "alert_triggered"]
    assert result.alerts[0].version == paused.version


@pytest.mark.asyncio
@pytest.mark.parametrize("chart_symbol", ["binance:usdm:BTCUSDT", "index:index:SPX"])
async def test_chart_alert_subscription_ignores_history_and_closes_cleanly(chart_symbol):
    class Market:
        queue = None
        unsubscribed = False

        def subscribe(self, symbol, timeframe, queue):
            assert (symbol, timeframe) == (chart_symbol, "1d" if chart_symbol.startswith("index:") else "1m")
            self.queue = queue

        def unsubscribe(self, symbol, timeframe, queue):
            assert queue is self.queue
            self.unsubscribed = True

    class Repository:
        def list_enabled_alerts(self):
            return [{"id": "alert", "configuration": {"chartSymbolId": chart_symbol}}]

    market = Market()
    runtime = ChartPriceAlertRuntime(Repository(), market)
    prices, received = [], asyncio.Event()

    async def capture(symbol, price):
        prices.append(price)
        received.set()

    runtime.evaluate_price = capture
    await runtime.refresh()
    await asyncio.sleep(0)
    market.queue.put_nowait({"type": "bar", "bar": {"close": 200, "closed": True}})
    market.queue.put_nowait({"type": "bar", "live": True, "bar": {"close": 105, "closed": True}})
    await asyncio.wait_for(received.wait(), 2)
    await runtime.shutdown()
    assert prices == [105]
    assert market.unsubscribed
    assert not runtime.workers


def test_chart_crossing_and_repeat_cooldown():
    now = utc_now_naive()
    rule = {"operator": "crosses", "threshold": 100, "last_value": 90, "cooldown_minutes": 1}
    assert should_trigger(rule, 100, now)
    rule.update(last_value=110)
    assert should_trigger(rule, 100, now)
    rule.update(last_triggered_at=now)
    assert not should_trigger(rule, 90, now + timedelta(seconds=59))
    assert should_trigger(rule, 90, now + timedelta(seconds=60))


@pytest.mark.parametrize("price", [float("nan"), float("inf"), 0, -1])
def test_chart_alert_rejects_invalid_prices(price):
    with pytest.raises(ValueError):
        ResearchAlertCreateCommand(symbol="BTC/USDT", name="Invalid", metric="price", operator="crosses", threshold=price,
                                   configuration={"chartSymbolId": "binance:spot:BTCUSDT"})
