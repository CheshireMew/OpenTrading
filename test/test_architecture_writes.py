from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime
from threading import Barrier
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.domain.research import ResearchRevisionConflictError
from app.infra.db import schema
from app.infra.persistence.research_repository import ResearchRepository
from app.infra.persistence.market_screener_repository import MarketScreenerRepository
from app.infra.persistence.trade_signal_repository import TradeSignalRepository
from app.infra.persistence import research_rows, research_record_repository


def race(repository, check, action):
    barrier = Barrier(2)
    # Synchronize the actual pre-write read after the repository responsibility split.
    owners = [repository]
    if isinstance(repository, ResearchRepository):
        owners, check = [research_rows, research_record_repository], check.lstrip("_")
    original = getattr(owners[0], check)

    def synchronized(*args, **kwargs):
        result = original(*args, **kwargs)
        barrier.wait(timeout=10)
        return result

    def run(_):
        try:
            return action()
        except Exception as exc:
            return exc

    with ExitStack() as stack:
        for owner in owners:
            stack.enter_context(patch.object(owner, check, synchronized))
        with ThreadPoolExecutor(2) as pool:
            return list(pool.map(run, range(2)))


@pytest.mark.parametrize(
    "model,values,repository_type,check,method",
    [
        (schema.ResearchWatchlist, {"name": "List"}, ResearchRepository, "_require_row", "set_watchlist_archived"),
        (
            schema.ResearchWatchItem,
            {"watchlist_id": "list", "symbol": "BTC/USDT"},
            ResearchRepository,
            "_require_row",
            "set_watch_item_archived",
        ),
        (
            schema.ResearchNote,
            {"symbol": "BTC/USDT", "title": "Note", "occurred_at": datetime(2026, 1, 1)},
            ResearchRepository,
            "_require_row",
            "set_note_archived",
        ),
        (
            schema.ResearchAlertRule,
            {"symbol": "BTC/USDT", "name": "Alert", "metric": "price", "operator": "gt", "threshold": 100},
            ResearchRepository,
            "_require_row",
            "set_alert_archived",
        ),
        (
            schema.SavedMarketScreener,
            {"name": "Screen", "description": "", "filters": {}},
            MarketScreenerRepository,
            "_require",
            "set_screener_archived",
        ),
        (
            schema.TradeSignalRecord,
            {
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "source": "rules",
                "mode": "rules",
                "signal_status": "ready",
                "reason": "test",
                "market_snapshot": {},
            },
            TradeSignalRepository,
            "_require",
            "set_signal_archived",
        ),
    ],
)
def test_all_versioned_research_archives_are_atomic(
    installed_database_runtime, model, values, repository_type, check, method
):
    runtime = installed_database_runtime
    with runtime.session_scope() as session:
        session.add(schema.ResearchWatchlist(id="list", name="Parent"))
        session.flush()
        session.add(model(id="record", **values))
    repository = repository_type(runtime)
    results = race(repository, check, lambda: getattr(repository, method)("record", 1, True))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum(isinstance(value, ResearchRevisionConflictError) for value in results) == 1
    with runtime.session_scope() as session:
        assert session.get(model, "record").version == 2
        assert (
            session.scalar(select(schema.ResearchEvent).where(schema.ResearchEvent.entity_id == "record")) is not None
        )
