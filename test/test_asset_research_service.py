from types import SimpleNamespace

import pytest

from app.services.asset_research_service import AssetResearchService


class _Model:
    def __init__(self, payload=None, **attributes):
        self.payload = payload or {}
        for key, value in attributes.items():
            setattr(self, key, value)

    def model_dump(self, **_kwargs):
        return self.payload


class _Research:
    def get_workbench(self, **_kwargs):
        return {"items": [], "notes": [], "alerts": [], "events": []}


class _Signals:
    def list_signals(self, **_kwargs):
        return [], 0


class _Web3HeatRanks:
    async def get_web3_heat_rank_boards(self, **_kwargs):
        rank_payload = {
            "rank": 2,
            "symbol": "TOKEN",
            "chain_id": "56",
            "contract_address": "0xabc",
            "platform": "bsc",
            "heat_score": 91,
            "metrics": {"price": 1.2, "smart_money_risk_level": 2},
        }
        item = _Model(
            rank_payload,
            contract_address="0xabc",
            chain_id="56",
            platform="bsc",
        )
        return SimpleNamespace(boards={"heat_score_desc": SimpleNamespace(items=[item])})


class _Web3Tokens:
    async def get_dynamic(self, **_kwargs):
        return _Model({"price": 1.25, "holders": 1000})

    async def get_audit(self, **_kwargs):
        return _Model({"risk_level": 2, "risk_level_enum": "LOW", "risk_items": []})

    async def get_kline(self, **_kwargs):
        return _Model({
            "items": [
                {"open_time": 1_700_000_000_000, "open": 1, "high": 1.4, "low": 0.9, "close": 1.25, "volume": 20},
            ]
        })


@pytest.mark.asyncio
async def test_unified_asset_supports_direct_web3_rank_dynamic_audit_and_history():
    service = AssetResearchService(
        research_repository=_Research(),
        signal_repository=_Signals(),
        market_query_service=object(),
        index_data_service=object(),
        binance_market_service=object(),
        binance_web3_heat_rank_service=_Web3HeatRanks(),
        binance_web3_token_service=_Web3Tokens(),
        pair_compare_service=object(),
    )

    result = await service.get_asset(
        symbol="0xabc",
        timeframe="1h",
        history_days=30,
        asset_class="web3",
        chain_id="56",
        platform="bsc",
    )

    assert result.assetClass == "web3"
    assert result.currentPrice == 1.25
    assert result.marketContext["web3Rank"]["rank"] == 2
    assert result.marketContext["web3Audit"]["risk_level"] == 2
    assert result.history[0].close == 1.25


class _MarketQuery:
    async def get_realtime(self, **_kwargs):
        return SimpleNamespace(current_price=100, indicators=None, kline_data=[])


class _Snapshot:
    async def get_market_page_snapshot_data(self):
        return {
            "updated_at": 1,
            "spot_ticker": {"items": [{"symbol": "ETHUSDT", "last_price": 100}]},
            "usdm_ticker": {"items": []},
            "usdm_mark": {"items": []},
        }


class _Page:
    async def get_page(self, **_kwargs):
        return _Model({
            "monitor": {"items": [{"symbol": "ETHUSDT", "natural_score": 70}]},
            "spot_boards": {},
            "contract_boards": {},
        })


class _PairCompare:
    def compare_pairs(self, *_args):
        return {
            "timeframe": "1h",
            "statistics": {"aligned_points": 100, "excess_return_pct": 4.2},
        }


@pytest.mark.asyncio
async def test_unified_crypto_asset_exposes_breakout_and_benchmark_statistics():
    service = AssetResearchService(
        research_repository=_Research(),
        signal_repository=_Signals(),
        market_query_service=_MarketQuery(),
        index_data_service=object(),
        binance_market_service=SimpleNamespace(snapshot_service=_Snapshot(), page=_Page()),
        binance_web3_heat_rank_service=object(),
        binance_web3_token_service=object(),
        pair_compare_service=_PairCompare(),
    )

    result = await service.get_asset(symbol="ETH/USDT", timeframe="1h", history_days=90)

    assert result.marketContext["breakoutMonitor"]["natural_score"] == 70
    assert result.marketContext["benchmarkComparison"]["benchmarkSymbol"] == "BTC/USDT"
    assert result.marketContext["benchmarkComparison"]["statistics"]["excess_return_pct"] == 4.2
