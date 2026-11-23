from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.contracts.research import ResearchArchiveCommand
from app.infra.persistence.trade_signal_repository import TradeSignalRepository
from app.services.trade_signal_evaluation_runtime import TradeSignalEvaluationRuntime
from app.services.trade_signal_service import TradeSignalService


def _payload(**updates):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    entry_time = int((now - timedelta(hours=3)).replace(tzinfo=timezone.utc).timestamp() * 1000)
    payload = {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "source": "rules",
        "mode": "rules",
        "signal_status": "ready",
        "side": "long",
        "entry": 100.0,
        "target": 110.0,
        "stop": 95.0,
        "risk_reward": 2.0,
        "confidence": 72,
        "risk_amount": 50.0,
        "style": "Intraday",
        "strategy": "Trend",
        "reason": "test",
        "error_code": None,
        "current_price": 100.0,
        "entry_time": entry_time,
        "market_snapshot": {"indicators": {"rsi": 55}},
        "outcome_status": "pending",
        "forward_returns": {},
        "expires_at": now + timedelta(days=7),
    }
    payload.update(updates)
    return payload


class FakeMarketQuery:
    def __init__(self, rows):
        self.rows = rows

    async def get_full_history(self, **_kwargs):
        return SimpleNamespace(items=self.rows, coverage=SimpleNamespace(complete=True, missing_ranges=[]))


@pytest.mark.asyncio
async def test_expiry_excludes_later_target_and_requires_complete_prior_history():
    start = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    signal = {"symbol": "BTC/USDT", "timeframe": "1h", "entryTime": start, "entry": 100, "target": 110,
              "stop": 90, "side": "long", "expiresAt": datetime(2026, 1, 1, 1)}
    def row(offset, high):
        return SimpleNamespace(timestamp=start + offset * 3_600_000, open=100, high=high, low=99, close=100, volume=1)
    market = FakeMarketQuery([row(0, 105), row(2, 120)])
    runtime = TradeSignalEvaluationRuntime(repository=None, market_query_service=market)
    result = await runtime._evaluate_signal(signal, datetime(2026, 1, 1, 3))
    assert result["outcomeStatus"] == "expired"
    assert result["targetHitAt"] is None
    market.rows = [row(2, 120)]
    assert (await runtime._evaluate_signal(signal, datetime(2026, 1, 1, 3)))["outcomeStatus"] == "unavailable"


@pytest.mark.asyncio
async def test_coverage_gap_prevents_claiming_a_target_hit():
    start = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    signal = {"symbol": "BTC/USDT", "timeframe": "1h", "entryTime": start, "entry": 100, "target": 110,
              "stop": 90, "side": "long", "expiresAt": datetime(2026, 1, 1, 4)}
    class Incomplete:
        async def get_full_history(self, **kwargs):
            assert kwargs["end_date"] == "2026-01-01"
            return SimpleNamespace(items=[SimpleNamespace(timestamp=start + 3_600_000, high=120, low=99, close=110)],
                coverage=SimpleNamespace(complete=False, missing_ranges=[SimpleNamespace(start_ts=start, end_ts=start + 3_600_000)]))
    runtime = TradeSignalEvaluationRuntime(repository=None, market_query_service=Incomplete())
    assert (await runtime._evaluate_signal(signal, datetime(2026, 1, 1, 3)))["outcomeStatus"] == "unavailable"


@pytest.mark.asyncio
async def test_signal_evaluator_records_target_mfe_mae_and_forward_returns(installed_database_runtime):
    repository = TradeSignalRepository(installed_database_runtime)
    signal = repository.create_signal(_payload())
    start = signal["entryTime"]
    rows = [
        SimpleNamespace(timestamp=start, open=100, high=104, low=98, close=102, volume=1),
        SimpleNamespace(timestamp=start + 3_600_000, open=102, high=111, low=101, close=110, volume=1),
        SimpleNamespace(timestamp=start + 4 * 3_600_000, open=110, high=114, low=109, close=112, volume=1),
        SimpleNamespace(timestamp=start + 24 * 3_600_000, open=112, high=113, low=108, close=109, volume=1),
    ]
    runtime = TradeSignalEvaluationRuntime(repository=repository, market_query_service=FakeMarketQuery(rows))

    result = await runtime.evaluate_once(signal_id=signal["id"], force=True)
    evaluated = repository.get_signal(signal["id"])

    assert result.resolvedCount == 1
    assert evaluated["outcomeStatus"] == "target_hit"
    assert evaluated["mfePct"] == pytest.approx(11)
    assert evaluated["maePct"] == pytest.approx(-2)
    assert evaluated["forwardReturns"]["1h"] == pytest.approx(2)
    assert evaluated["forwardReturns"]["24h"] is None  # The supplied 24h row is in the future.


@pytest.mark.asyncio
async def test_same_candle_target_and_stop_is_ambiguous(installed_database_runtime):
    repository = TradeSignalRepository(installed_database_runtime)
    signal = repository.create_signal(_payload())
    row = SimpleNamespace(timestamp=signal["entryTime"], open=100, high=111, low=94, close=100, volume=1)
    runtime = TradeSignalEvaluationRuntime(repository=repository, market_query_service=FakeMarketQuery([row]))

    await runtime.evaluate_once(signal_id=signal["id"], force=True)

    assert repository.get_signal(signal["id"])["outcomeStatus"] == "ambiguous"


def test_signal_stats_and_recoverable_archive(installed_database_runtime):
    repository = TradeSignalRepository(installed_database_runtime)
    service = TradeSignalService(repository)
    first = repository.create_signal(_payload())
    second = repository.create_signal(_payload(source="ai", mode="ai", strategy="Breakout"))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repository.record_evaluation(first["id"], {"outcomeStatus": "target_hit", "evaluatedAt": now})
    repository.record_evaluation(second["id"], {"outcomeStatus": "stop_hit", "evaluatedAt": now})

    stats = service.get_stats()
    assert stats.overall.resolved == 2
    assert stats.overall.winRatePct == 50
    bucket = next(item for item in stats.confidenceCalibration if item.key == "60-79")
    assert bucket.total == 2
    assert bucket.resolved == 2
    assert bucket.winRatePct == 50
    assert bucket.expectedWinRatePct == 72
    assert bucket.calibrationGapPct == -22

    archived = service.archive(first["id"], ResearchArchiveCommand(expectedVersion=1), archived=True)
    assert archived.archivedAt is not None
    restored = service.archive(first["id"], ResearchArchiveCommand(expectedVersion=2), archived=False)
    assert restored.archivedAt is None
