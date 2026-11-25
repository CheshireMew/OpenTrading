from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.dependencies import get_asset_research_service, get_tools_app_service
from app.domain.market.candles import RecentCandles
from app.infra.persistence.research_repository import ResearchRepository
from app.main import app
from app.services.asset_research_service import AssetResearchService
from app.services.market.binance_market_normalizers import normalize_mark_price_list, normalize_ticker_item
from app.services.market.history_range_coordinator import OhlcvRangeResult
from app.services.tools.app_service import ToolsAppService
from app.services.tools.dca_service import DCAService
from test.test_asset_research_service import _MarketQuery, _Page, _PairCompare, _Signals


def export_fixture(name, data):
    if directory := os.environ.get("OPENTRADING_CONTRACT_FIXTURES"):
        Path(directory).joinpath(name).write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def test_correct_dca_reaches_the_public_tools_response(api_harness, monkeypatch):
    fixed = datetime.now(timezone.utc).replace(hour=23, minute=30, second=0, microsecond=0)
    monkeypatch.setattr("app.services.tools.app_service.now_in_timezone", lambda _: fixed)
    monkeypatch.setattr("app.services.tools.dca_service.now_in_timezone", lambda _: fixed)
    rows = [[int(day.timestamp() * 1000), price, price, price, price, 1000]
            for day, price in [(fixed.replace(minute=0) - timedelta(days=1), 100), (fixed.replace(minute=0), 1000)]]

    class Source:
        def load_ohlcv_range(self, *_args):
            return OhlcvRangeResult(rows, [])

        def get_recent_candle_snapshot(self, *_args, **_kwargs):
            return RecentCandles(rows[-1:], int(datetime.now(timezone.utc).timestamp() * 1000), "controlled-exchange")

    class Cache:
        keys = []

        async def aget(self, key):
            self.keys.append(key)
            return {"old_incorrect_result": True} if not key.startswith("dca:v3:") else None

        async def aset(self, *_args, **_kwargs):
            pass

    cache = Cache()
    service = ToolsAppService(DCAService(Source(), object(), object()), object(), cache)
    app.dependency_overrides[get_tools_app_service] = lambda: service
    client = api_harness["client"]
    command = {"symbol": "BTC/USDT", "start_date": (fixed - timedelta(days=1)).date().isoformat(), "amount": 1000,
               "investment_time": "23:00", "timezone": "UTC", "strategy": "value_averaging", "strategy_params": {"fee_rate": .001}}
    response = client.post("/api/v1/tools/dca_simulate", json=command)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["total_coins"] == 2
    assert value["final_value"] == 2000
    assert value["total_invested"] == -6982.01
    assert value["history"][-1]["coins"] == 2
    assert cache.keys and all(key.startswith("dca:v3:") for key in cache.keys)
    export_fixture("dca.json", {"command": command, "response": value})
    export_fixture("tools-contract.json", client.get("/api/v1/tools/contract").json())
    export_fixture("symbols.json", client.get("/api/v1/symbols").json())


@pytest.mark.parametrize("case,spot,futures,funding", [
    ("values", "1.25", "-2.5", "0.0001"), ("zero", "0", "0", "0"), ("missing", None, None, None),
])
def test_normalized_asset_context_reaches_the_http_contract(
    api_harness, installed_database_runtime, case, spot, futures, funding,
):
    class Snapshot:
        async def get_market_page_snapshot_data(self):
            return {
                "spot_ticker": {"items": [normalize_ticker_item({"symbol": "ETHUSDT", "priceChangePercent": spot})]},
                "usdm_ticker": {"items": [normalize_ticker_item({"symbol": "ETHUSDT", "priceChangePercent": futures})]},
                "usdm_mark": normalize_mark_price_list("usdm", {"symbol": "ETHUSDT", "lastFundingRate": funding}),
            }
    service = AssetResearchService(
        research_repository=ResearchRepository(installed_database_runtime), signal_repository=_Signals(),
        market_query_service=_MarketQuery(), index_data_service=object(),
        binance_market_service=SimpleNamespace(snapshot_service=Snapshot(), page=_Page()),
        binance_web3_heat_rank_service=object(), binance_web3_token_service=object(), pair_compare_service=_PairCompare(),
    )
    app.dependency_overrides[get_asset_research_service] = lambda: service
    response = api_harness["client"].get("/api/v1/research/assets/ETH%2FUSDT")
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["marketContext"]["spot_ticker"]["price_change_pct"] == (float(spot) if spot is not None else None)
    assert value["marketContext"]["usdm_ticker"]["price_change_pct"] == (float(futures) if futures is not None else None)
    assert value["marketContext"]["usdm_mark"]["last_funding_rate"] == (float(funding) if funding is not None else None)
    assert value["marketContext"]["benchmarkComparison"]["statistics"]["excess_return_pct"] == 4.2
    export_fixture(f"asset-{case}.json", value)
