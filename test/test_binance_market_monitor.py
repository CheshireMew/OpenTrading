from __future__ import annotations

import asyncio
import time

import pytest

from app.contracts.dto.binance.common import BinanceTickerStatsResponse
from app.contracts.dto.binance.usdm import BinanceMarkPriceResponse, BinanceOpenInterestStatsResponse
from app.services.market import binance_contract_oi_enricher as oi_enricher_module
from app.services.market.binance_market_intel_service import BinanceMarketIntelService
from app.infra.persistence.market.binance_market_research_store import BinanceMarketResearchStore


def make_market_intel_service(installed_database_runtime) -> BinanceMarketIntelService:
    return BinanceMarketIntelService(
        research_store=BinanceMarketResearchStore(database_runtime=installed_database_runtime),
    )


def make_breakout_klines(start_price: float, bars: int = 80) -> list[dict]:
    rows: list[dict] = []
    price = start_price
    for index in range(bars):
        open_price = price
        change = 0.0038 if index % 6 else 0.0014
        close_price = open_price * (1.0 + change)
        high_price = close_price * 1.002
        low_price = open_price * 0.998
        rows.append(
            {
                "open_time": 1717000000000 + index * 900000,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": 1_000_000 + index * 1000,
                "close_time": 1717000000000 + (index + 1) * 900000 - 1,
            }
        )
        price = close_price
    return rows


@pytest.mark.asyncio
async def test_market_breakout_monitor_unifies_and_scores_candidates(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)

    async def fake_spot_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "spot",
            "items": [
                {"symbol": "DOGEUSDT", "last_price": 0.164, "price_change_pct": 8.6, "quote_volume": 310_000_000.0},
                {"symbol": "XRPUPUSDT", "last_price": 0.42, "price_change_pct": 18.0, "quote_volume": 60_000_000.0},
                {"symbol": "BTCFDUSD", "last_price": 68000.0, "price_change_pct": 5.5, "quote_volume": 200_000_000.0},
            ],
        })

    async def fake_usdm_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "SUIUSDT", "last_price": 1.82, "price_change_pct": 6.2, "quote_volume": 180_000_000.0},
                {"symbol": "BTCUSDT_260626", "last_price": 70200.0, "price_change_pct": 7.0, "quote_volume": 90_000_000.0},
            ],
        })

    async def fake_usdm_mark_price(**kwargs):
        return BinanceMarkPriceResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "SUIUSDT", "mark_price": 1.81, "last_funding_rate": 0.00012},
                {"symbol": "BTCUSDT_260626", "mark_price": 70180.0, "last_funding_rate": 0.00005},
            ],
        })

    async def fake_spot_klines(**kwargs):
        return {"exchange": "binance", "market": "spot", "symbol": "DOGEUSDT", "interval": "15m", "items": make_breakout_klines(0.12)}

    async def fake_usdm_klines(**kwargs):
        return {"exchange": "binance", "market": "usdm", "symbol": "SUIUSDT", "interval": "15m", "items": make_breakout_klines(1.35)}

    monkeypatch.setattr(service.spot, "get_ticker_24hr", fake_spot_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_ticker_24hr", fake_usdm_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_mark_price", fake_usdm_mark_price)
    monkeypatch.setattr(service.spot, "get_klines", fake_spot_klines)
    monkeypatch.setattr(service.usdm, "get_klines", fake_usdm_klines)

    page = (await service.page.refresh_page((5.0, 10, "USDT"))).model_dump()
    response = page["monitor"]

    assert response["summary"]["monitored_count"] == 2
    assert response["summary"]["spot_count"] == 1
    assert response["summary"]["contract_count"] == 1

    symbols = {item["symbol"] for item in response["items"]}
    assert symbols == {"DOGEUSDT", "SUIUSDT"}

    spot_item = next(item for item in response["items"] if item["symbol"] == "DOGEUSDT")
    assert spot_item["structure_ok"] is True
    assert spot_item["momentum_ok"] is True
    assert spot_item["verdict"] == "优先关注"
    assert spot_item["follow_status"] in {"继续上行", "高位蓄势"}
    assert spot_item["reasons"]


@pytest.mark.asyncio
async def test_market_page_payload_returns_partial_data_when_a_source_fails(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)

    async def fake_spot_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "spot",
            "items": [
                {"symbol": "DOGEUSDT", "last_price": 0.164, "price_change_pct": 8.6, "quote_volume": 310_000_000.0},
            ],
        })

    async def fake_usdm_ticker_24hr(**kwargs):
        raise RuntimeError("upstream timeout")

    async def fake_usdm_mark_price(**kwargs):
        return BinanceMarkPriceResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [],
        })

    async def fake_spot_klines(**kwargs):
        return {"exchange": "binance", "market": "spot", "symbol": "DOGEUSDT", "interval": "15m", "items": make_breakout_klines(0.12)}

    monkeypatch.setattr(service.spot, "get_ticker_24hr", fake_spot_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_ticker_24hr", fake_usdm_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_mark_price", fake_usdm_mark_price)
    monkeypatch.setattr(service.spot, "get_klines", fake_spot_klines)

    response = (await service.page.refresh_page((5.0, 24, "USDT"))).model_dump()

    assert response["load_errors"] == ["U本位24H"]
    assert response["spot_boards"]["price_change_pct_desc"]["items"]
    assert response["contract_boards"]["price_change_pct_desc"]["items"] == []
    assert response["monitor"]["summary"]["monitored_count"] == 1
    assert {item["symbol"] for item in response["monitor"]["items"]} == {"DOGEUSDT"}


@pytest.mark.asyncio
async def test_market_page_request_reads_snapshot_without_expensive_refresh(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)

    async def fake_spot_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "spot",
            "items": [
                {"symbol": "DOGEUSDT", "last_price": 0.164, "price_change_pct": 8.6, "quote_volume": 310_000_000.0},
            ],
        })

    async def fake_usdm_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "SUIUSDT", "last_price": 1.82, "price_change_pct": 6.2, "quote_volume": 180_000_000.0},
            ],
        })

    async def fake_usdm_mark_price(**kwargs):
        return BinanceMarkPriceResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "SUIUSDT", "mark_price": 1.81, "last_funding_rate": 0.00012},
            ],
        })

    async def fail_if_called(**kwargs):
        raise AssertionError("page request must not trigger expensive refresh work")

    await service.snapshot_service.seed(
        spot_ticker_loader=fake_spot_ticker_24hr,
        usdm_ticker_loader=fake_usdm_ticker_24hr,
        usdm_mark_loader=fake_usdm_mark_price,
    )
    monkeypatch.setattr(service.spot, "get_klines", fail_if_called)
    monkeypatch.setattr(service.usdm, "get_klines", fail_if_called)
    monkeypatch.setattr(service.usdm, "get_open_interest_stats", fail_if_called)

    response = (await asyncio.wait_for(
        service.page.get_page(min_rise_pct=5.0, limit=24, quote_asset="USDT"),
        timeout=0.2,
    )).model_dump()

    assert response["refresh_status"]["monitor_ready"] is False
    assert response["spot_boards"]["price_change_pct_desc"]["items"][0]["symbol"] == "DOGEUSDT"
    assert response["contract_boards"]["price_change_pct_desc"]["items"][0]["symbol"] == "SUIUSDT"
    assert response["contract_boards"]["price_change_pct_desc"]["items"][0]["oi_change_24h_pct"] is None


@pytest.mark.asyncio
async def test_market_page_request_is_not_blocked_by_background_oi_cache_reads(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)
    loop = asyncio.get_running_loop()
    cached_read_started = asyncio.Event()

    async def fake_spot_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "spot",
            "items": [],
        })

    async def fake_usdm_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "AUSDT", "last_price": 1.0, "price_change_pct": 8.0, "quote_volume": 20.0},
                {"symbol": "BUSDT", "last_price": 2.0, "price_change_pct": 7.0, "quote_volume": 10.0},
            ],
        })

    async def fake_usdm_mark_price(**kwargs):
        return BinanceMarkPriceResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "AUSDT", "mark_price": 1.01, "last_funding_rate": 0.0003},
                {"symbol": "BUSDT", "mark_price": 2.01, "last_funding_rate": -0.0002},
            ],
        })

    async def fake_klines(**kwargs):
        return {
            "exchange": "binance",
            "market": "usdm",
            "symbol": kwargs.get("symbol", "AUSDT"),
            "interval": kwargs.get("interval", "15m"),
            "items": make_breakout_klines(1.0),
        }

    def slow_cached_open_interest_stats(**kwargs):
        loop.call_soon_threadsafe(cached_read_started.set)
        time.sleep(0.5)
        return BinanceOpenInterestStatsResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": kwargs["symbol"], "sum_open_interest": 100.0 + index, "sum_open_interest_value": 1000.0 + index, "timestamp": 1717000000000 + index * 3600000}
                for index in range(25)
            ],
        })

    await service.snapshot_service.seed(
        spot_ticker_loader=fake_spot_ticker_24hr,
        usdm_ticker_loader=fake_usdm_ticker_24hr,
        usdm_mark_loader=fake_usdm_mark_price,
    )
    monkeypatch.setattr(service.usdm, "get_cached_open_interest_stats", slow_cached_open_interest_stats)
    monkeypatch.setattr(service.usdm, "get_klines", fake_klines)

    refresh_task = asyncio.create_task(service.page.refresh_page((5.0, 24, "USDT")))
    await asyncio.wait_for(cached_read_started.wait(), timeout=1.0)

    response = await asyncio.wait_for(
        service.page.get_page(min_rise_pct=7.0, limit=24, quote_asset="USDT"),
        timeout=0.2,
    )
    response = response.model_dump()

    await asyncio.wait_for(refresh_task, timeout=2.0)
    assert response["refresh_status"]["monitor_ready"] is False
    assert response["contract_boards"]["price_change_pct_desc"]["items"]


@pytest.mark.asyncio
async def test_market_page_payload_reuses_background_snapshot(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)
    kline_calls = 0

    async def fake_spot_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "spot",
            "items": [
                {"symbol": "DOGEUSDT", "last_price": 0.164, "price_change_pct": 8.6, "quote_volume": 310_000_000.0},
            ],
        })

    async def fake_usdm_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [],
        })

    async def fake_usdm_mark_price(**kwargs):
        return BinanceMarkPriceResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [],
        })

    async def fake_spot_klines(**kwargs):
        nonlocal kline_calls
        kline_calls += 1
        return {
            "exchange": "binance",
            "market": "spot",
            "symbol": "DOGEUSDT",
            "interval": kwargs.get("interval", "15m"),
            "items": make_breakout_klines(0.12),
        }

    monkeypatch.setattr(service.spot, "get_ticker_24hr", fake_spot_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_ticker_24hr", fake_usdm_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_mark_price", fake_usdm_mark_price)
    monkeypatch.setattr(service.spot, "get_klines", fake_spot_klines)

    await service.page.refresh_page((5.0, 24, "USDT"))
    first = (await service.page.get_page(min_rise_pct=5.0, limit=24, quote_asset="USDT")).model_dump()
    second = (await service.page.get_page(min_rise_pct=5.0, limit=24, quote_asset="USDT")).model_dump()

    assert kline_calls == 2
    assert first["updated_at"] == second["updated_at"]
    assert first["monitor"]["items"] == second["monitor"]["items"]


@pytest.mark.asyncio
async def test_market_page_payload_returns_prebuilt_sorted_boards(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)

    async def fake_spot_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "spot",
            "items": [
                {"symbol": "LOWUSDT", "last_price": 1.0, "price_change_pct": -3.0, "quote_volume": 50.0},
                {"symbol": "HIGHUSDT", "last_price": 2.0, "price_change_pct": 12.0, "quote_volume": 20.0},
                {"symbol": "BTCFDUSD", "last_price": 68000.0, "price_change_pct": 30.0, "quote_volume": 1000.0},
            ],
        })

    async def fake_usdm_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "AUSDT", "last_price": 1.0, "price_change_pct": 5.0, "quote_volume": 10.0},
                {"symbol": "BUSDT", "last_price": 2.0, "price_change_pct": 7.0, "quote_volume": 20.0},
            ],
        })

    async def fake_usdm_mark_price(**kwargs):
        return BinanceMarkPriceResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "AUSDT", "mark_price": 1.01, "last_funding_rate": 0.0003},
                {"symbol": "BUSDT", "mark_price": 2.01, "last_funding_rate": -0.0002},
            ],
        })

    async def fake_open_interest_stats(**kwargs):
        base = 100.0 if kwargs["symbol"] == "AUSDT" else 200.0
        change = 12.0 if kwargs["symbol"] == "AUSDT" else 5.0
        items = [
            {
                "symbol": kwargs["symbol"],
                "sum_open_interest": base + index * change,
                "sum_open_interest_value": (base + index * change) * 1000,
                "timestamp": 1717000000000 + index * 3600000,
            }
            for index in range(25)
        ]
        return BinanceOpenInterestStatsResponse.model_validate({"exchange": "binance", "market": "usdm", "items": items})

    async def fake_klines(**kwargs):
        return {
            "exchange": "binance",
            "market": kwargs.get("market", "spot"),
            "symbol": kwargs.get("symbol", "HIGHUSDT"),
            "interval": kwargs.get("interval", "15m"),
            "items": make_breakout_klines(1.0),
        }

    monkeypatch.setattr(service.spot, "get_ticker_24hr", fake_spot_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_ticker_24hr", fake_usdm_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_mark_price", fake_usdm_mark_price)
    monkeypatch.setattr(service.usdm, "get_open_interest_stats", fake_open_interest_stats)
    monkeypatch.setattr(service.spot, "get_klines", fake_klines)
    monkeypatch.setattr(service.usdm, "get_klines", fake_klines)

    response = (await service.page.refresh_page((5.0, 2, "USDT"))).model_dump()

    assert [item["symbol"] for item in response["spot_boards"]["price_change_pct_desc"]["items"][:2]] == ["HIGHUSDT", "LOWUSDT"]
    assert [item["symbol"] for item in response["spot_boards"]["price_change_pct_asc"]["items"][:2]] == ["LOWUSDT", "HIGHUSDT"]
    assert [item["symbol"] for item in response["contract_boards"]["funding_rate_pct_desc"]["items"]] == ["AUSDT", "BUSDT"]
    assert response["contract_boards"]["funding_rate_pct_desc"]["items"][0]["funding_rate_pct"] == 0.03
    assert [item["symbol"] for item in response["contract_boards"]["oi_change_24h_pct_desc"]["items"]] == ["AUSDT", "BUSDT"]
    assert response["contract_boards"]["oi_change_24h_pct_desc"]["items"][0]["oi_change_24h_pct"] > 100


@pytest.mark.asyncio
async def test_market_page_payload_does_not_wait_unbounded_for_oi_enrichment(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)

    async def fake_spot_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "spot",
            "items": [],
        })

    async def fake_usdm_ticker_24hr(**kwargs):
        return BinanceTickerStatsResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "AUSDT", "last_price": 1.0, "price_change_pct": 5.0, "quote_volume": 20.0},
                {"symbol": "BUSDT", "last_price": 2.0, "price_change_pct": 4.0, "quote_volume": 10.0},
            ],
        })

    async def fake_usdm_mark_price(**kwargs):
        return BinanceMarkPriceResponse.model_validate({
            "exchange": "binance",
            "market": "usdm",
            "items": [
                {"symbol": "AUSDT", "mark_price": 1.01, "last_funding_rate": 0.0003},
                {"symbol": "BUSDT", "mark_price": 2.01, "last_funding_rate": -0.0002},
            ],
        })

    async def slow_open_interest_stats(**kwargs):
        await asyncio.sleep(1)
        return BinanceOpenInterestStatsResponse.model_validate({"exchange": "binance", "market": "usdm", "items": []})

    monkeypatch.setattr(oi_enricher_module, "CONTRACT_OI_REQUEST_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(oi_enricher_module, "CONTRACT_OI_ENRICHMENT_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(service.spot, "get_ticker_24hr", fake_spot_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_ticker_24hr", fake_usdm_ticker_24hr)
    monkeypatch.setattr(service.usdm, "get_mark_price", fake_usdm_mark_price)
    monkeypatch.setattr(service.usdm, "get_open_interest_stats", slow_open_interest_stats)

    response = (await asyncio.wait_for(
        service.page.refresh_page((50.0, 2, "USDT")),
        timeout=0.5,
    )).model_dump()

    rows = response["contract_boards"]["price_change_pct_desc"]["items"]
    assert [item["symbol"] for item in rows] == ["AUSDT", "BUSDT"]
    assert [item["oi_change_24h_pct"] for item in rows] == [None, None]


@pytest.mark.asyncio
async def test_dynamic_binance_chart_uses_requested_market_and_maps_ohlcv(monkeypatch, installed_database_runtime):
    service = make_market_intel_service(installed_database_runtime)
    captured: dict[str, object] = {}

    async def fake_usdm_klines(**kwargs):
        captured.update(kwargs)
        return {
            "exchange": "binance",
            "market": "usdm",
            "symbol": kwargs["symbol"],
            "interval": kwargs["interval"],
            "items": make_breakout_klines(2.0, bars=2),
        }

    monkeypatch.setattr(service.usdm, "get_klines", fake_usdm_klines)
    response = await service.page.get_chart_klines(
        market="usdm",
        symbol="PROMUSDT",
        interval="15m",
        limit=2,
        end_time=1718000000000,
    )

    assert captured == {
        "symbol": "PROMUSDT",
        "interval": "15m",
        "limit": 2,
        "start_time": None,
        "end_time": 1718000000000,
    }
    assert response.symbol == "PROMUSDT"
    assert response.timeframe == "15m"
    assert [item.timestamp for item in response.items] == [1717000000000, 1717000900000]
