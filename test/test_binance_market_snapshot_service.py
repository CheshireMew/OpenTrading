from __future__ import annotations

import pytest

from app.services.market.binance_market_snapshot_service import BinanceMarketSnapshotService


@pytest.mark.asyncio
async def test_snapshot_service_seeds_and_returns_local_market_snapshot():
    service = BinanceMarketSnapshotService()

    async def spot_loader():
        return {
            "exchange": "binance",
            "market": "spot",
            "items": [
                {"symbol": "BTCUSDT", "last_price": 100.0, "price_change_pct": 5.0, "quote_volume": 10.0},
                {"symbol": "ETHUSDT", "last_price": 10.0, "price_change_pct": -8.0, "quote_volume": 20.0},
            ],
        }

    async def usdm_ticker_loader():
        return {
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "SOLUSDT", "last_price": 20.0, "price_change_pct": 9.0, "quote_volume": 30.0},
            ],
        }

    async def usdm_mark_loader():
        return {
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "SOLUSDT", "mark_price": 20.1, "last_funding_rate": 0.0012},
            ],
        }

    await service.seed(
        spot_ticker_loader=spot_loader,
        usdm_ticker_loader=usdm_ticker_loader,
        usdm_mark_loader=usdm_mark_loader,
    )

    snapshot = (await service.get_market_page_snapshot())

    assert snapshot["load_errors"] == []
    assert [item["symbol"] for item in snapshot["spot_ticker"]["items"]] == ["ETHUSDT", "BTCUSDT"]
    assert snapshot["usdm_ticker"]["items"][0]["symbol"] == "SOLUSDT"
    assert snapshot["usdm_mark"]["items"][0]["last_funding_rate"] == 0.0012
    assert await service.get_current_price("BTC/USDT") == 100.0
    assert await service.get_current_price("binance:usdm:SOLUSDT") == 20.1


@pytest.mark.asyncio
async def test_snapshot_service_normalizes_websocket_events():
    service = BinanceMarketSnapshotService()

    await service._apply_spot_ticker_events([
        {"s": "DOGEUSDT", "c": "0.16", "P": "12.4", "q": "1000000", "n": 42},
    ])
    await service._apply_usdm_mark_events([
        {"s": "DOGEUSDT", "p": "0.161", "i": "0.160", "r": "-0.0002", "T": 1717000000000},
    ])

    snapshot = (await service.get_market_page_snapshot())

    spot_item = snapshot["spot_ticker"]["items"][0]
    mark_item = snapshot["usdm_mark"]["items"][0]
    assert spot_item["symbol"] == "DOGEUSDT"
    assert spot_item["last_price"] == 0.16
    assert spot_item["price_change_pct"] == 12.4
    assert spot_item["count"] == 42
    assert mark_item["mark_price"] == 0.161
    assert mark_item["last_funding_rate"] == -0.0002


@pytest.mark.asyncio
async def test_usdm_snapshot_ignores_coin_m_events():
    service = BinanceMarketSnapshotService()

    await service._apply_usdm_ticker_events([
        {"s": "BTCUSDT", "c": "62000", "st": 1},
        {"s": "BTCUSD_PERP", "c": "62100", "st": 2},
    ])
    await service._apply_usdm_mark_events([
        {"s": "BTCUSDT", "p": "62010", "st": 1},
        {"s": "BTCUSD_PERP", "p": "62110", "st": 2},
    ])

    snapshot = await service.get_market_page_snapshot()

    assert [item["symbol"] for item in snapshot["usdm_ticker"]["items"]] == ["BTCUSDT"]
    assert [item["symbol"] for item in snapshot["usdm_mark"]["items"]] == ["BTCUSDT"]
