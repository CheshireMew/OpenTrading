from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.contracts.research import (
    ResearchArchiveCommand,
    SavedMarketScreenerCreateCommand,
    SavedMarketScreenerUpdateCommand,
)
from app.infra.persistence.market_screener_repository import MarketScreenerRepository
from app.services.market_screener_service import MarketScreenerService


@pytest.mark.asyncio
async def test_alerts_screeners_and_http_share_units_and_market_identity():
    from unittest.mock import AsyncMock
    from app.routers.market.binance_page import get_market_observations
    from app.services.market.binance_market_observations import BinanceMarketObservationService
    from app.services.research_alert_runtime import ResearchAlertRuntime

    snapshot = {"spot_ticker": {"items": [{"symbol": "BTCUSDT", "last_price": 90}]},
                "usdm_ticker": {"items": [{"symbol": "BTCUSDT", "last_price": 110}]},
                "usdm_mark": {"items": [{"symbol": "BTCUSDT", "last_funding_rate": 0.0001}]}}
    page = SimpleNamespace(monitor=SimpleNamespace(items=[]), contract_boards={})
    snapshots = SimpleNamespace(get_market_page_snapshot_data=AsyncMock(return_value=snapshot))
    pages = SimpleNamespace(get_page=AsyncMock(return_value=page))
    service = SimpleNamespace(observations=BinanceMarketObservationService(snapshots, pages))
    http = await get_market_observations(symbols="BTCUSDT,binance:usdm:BTCUSDT", extended=True, service=service)
    alert = ResearchAlertRuntime(research_repository=object(), market_query_service=object(), binance_market_service=object())
    value = await alert._resolve_value({"symbol": "BTC/USDT", "metric": "funding_rate_pct"}, snapshot=snapshot, market_page=page)
    rows = MarketScreenerService._filter(snapshot, page, {"market": "usdm"})
    assert value == http["BTCUSDT"]["funding_rate_pct"] == rows[0]["fundingRatePct"] == pytest.approx(0.01)
    assert http["BTCUSDT"]["price"] == 90
    assert http["BINANCE:USDM:BTCUSDT"]["price"] == 110
    assert await alert._resolve_value({"symbol": "BTC/USDT:PERPETUAL", "metric": "price"}, snapshot=snapshot, market_page=page) == 110


def _command(name="Momentum"):
    return SavedMarketScreenerCreateCommand.model_validate(
        {
            "name": name,
            "filters": {
                "market": "all",
                "quoteAsset": "usdt",
                "minPriceChangePct": 5,
                "minQuoteVolume": 1_000_000,
                "maxFundingRatePct": 0.1,
                "minBreakoutScore": 60,
                "limit": 25,
            },
        }
    )


def test_delete_screener_removes_runs_and_timeline_but_keeps_other_screeners(installed_database_runtime):
    from sqlalchemy import select
    from app.domain.research import ResearchRevisionConflictError
    from app.infra.db.schema import MarketScreenerRun, ResearchEvent, SavedMarketScreener

    repository=MarketScreenerRepository(installed_database_runtime)
    created=repository.create_screener({"name":"Delete", "description":"", "filters":{}})
    other=repository.create_screener({"name":"Keep", "description":"", "filters":{}})
    run=repository.save_run(created["id"],{"filters_snapshot":{},"result_items":[],"result_count":0,"snapshot_as_of":datetime(2026,1,1),"evaluated_at":datetime(2026,1,1)}, expected_version=created["version"])
    with pytest.raises(ResearchRevisionConflictError):
        repository.delete_screener(created["id"],2)
    repository.delete_screener(created["id"],1)
    with installed_database_runtime.session_scope() as session:
        assert session.get(SavedMarketScreener,created["id"]) is None
        assert session.get(MarketScreenerRun,run["id"]) is None
        assert session.get(SavedMarketScreener,other["id"]) is not None
        assert not list(session.scalars(select(ResearchEvent).where(ResearchEvent.entity_id==created["id"])))


def test_saved_screener_is_versioned_archivable_and_replays_as_of(installed_database_runtime):
    repository = MarketScreenerRepository(installed_database_runtime)
    service = MarketScreenerService(repository=repository, binance_market_service=object())
    created = service.create(_command())
    updated = service.update(
        created.id,
        SavedMarketScreenerUpdateCommand(
            expectedVersion=created.version,
            **_command("Momentum v2").model_dump(),
        ),
    )
    first_time = datetime(2026, 1, 1, 12)
    second_time = first_time + timedelta(days=1)
    repository.save_run(
        created.id,
        {
            "filters_snapshot": updated.filters.model_dump(),
            "result_items": [{"symbol": "BTCUSDT"}],
            "result_count": 1,
            "snapshot_as_of": first_time,
            "evaluated_at": first_time,
        },
        expected_version=updated.version,
    )
    repository.save_run(
        created.id,
        {
            "filters_snapshot": updated.filters.model_dump(),
            "result_items": [{"symbol": "ETHUSDT"}],
            "result_count": 1,
            "snapshot_as_of": second_time,
            "evaluated_at": second_time,
        },
        expected_version=updated.version,
    )

    replay = repository.get_run_as_of(created.id, first_time + timedelta(hours=1))
    assert replay["resultItems"][0]["symbol"] == "BTCUSDT"
    assert replay["historicalReplay"] is True

    archived = service.archive(created.id, ResearchArchiveCommand(expectedVersion=updated.version), archived=True)
    assert archived.archivedAt is not None


def test_screener_filter_combines_snapshot_scores_funding_and_oi():
    snapshot = {
        "spot_ticker": {
            "items": [{"symbol": "BTCUSDT", "last_price": 100, "price_change_pct": 8, "quote_volume": 5_000_000}]
        },
        "usdm_ticker": {
            "items": [{"symbol": "ETHUSDT", "last_price": 50, "price_change_pct": 7, "quote_volume": 4_000_000}]
        },
        "usdm_mark": {"items": [{"symbol": "ETHUSDT", "funding_rate_pct": 0.02}]},
    }
    monitor = [
        SimpleNamespace(market="spot", symbol="BTCUSDT", natural_score=70, momentum_score=80, verdict="优先关注")
    ]
    contract = SimpleNamespace(symbol="ETHUSDT", oi_change_1h_pct=4)
    page = SimpleNamespace(
        monitor=SimpleNamespace(items=monitor), contract_boards={"oi": SimpleNamespace(items=[contract])}
    )
    filters = _command().filters.model_dump()

    result = MarketScreenerService._filter(snapshot, page, filters)

    assert [item["symbol"] for item in result] == ["BTCUSDT"]
    assert result[0]["breakoutScore"] == 80


class _RsiQuery:
    async def get_realtime(self, *, symbol, **_kwargs):
        values = {"BTC/USDT": 68.0, "ETH/USDT": 81.0}
        return SimpleNamespace(indicators=SimpleNamespace(rsi=values[symbol]))


class _Web3HeatRanks:
    async def get_web3_heat_rank_boards(self, **_kwargs):
        metrics = SimpleNamespace(
            percent_change_24h=12,
            volume_24h=2_000_000,
            smart_money_risk_level=2,
            price=0.5,
        )
        item = SimpleNamespace(
            symbol="TOKEN",
            contract_address="0xabc",
            chain_id="56",
            platform="bsc",
            heat_score=88,
            rank=3,
            metrics=metrics,
        )
        return SimpleNamespace(boards={"heat_score_desc": SimpleNamespace(items=[item])})


@pytest.mark.asyncio
async def test_screener_applies_rsi_and_web3_risk_filters():
    service = MarketScreenerService(
        repository=object(),
        binance_market_service=object(),
        market_query_service=_RsiQuery(),
        binance_web3_heat_rank_service=_Web3HeatRanks(),
    )
    exchange = await service._apply_rsi_filters(
        [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
        {"quoteAsset": "USDT", "minRsi": 60, "maxRsi": 70},
    )
    web3 = await service._load_web3_items(
        {
            "includeWeb3": True,
            "web3ChainId": "56",
            "maxWeb3RiskLevel": 2,
            "symbols": [],
            "limit": 30,
        }
    )

    assert exchange == [{"symbol": "BTCUSDT", "rsi": 68.0}]
    assert web3[0]["contractAddress"] == "0xabc"
    assert web3[0]["web3RiskLevel"] == 2
