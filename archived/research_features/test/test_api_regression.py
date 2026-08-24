from __future__ import annotations

from typing import Any

import pytest

from app.services.market.query_app_service import MarketQueryAppService
from test.regression_support import make_strategy_config


def make_backtest_start_payload() -> dict[str, Any]:
    return {
        "strategy_key": "ema_rsi_macd",
        "strategy_version": 2,
        "timeframe": "1h",
        "days": 180,
        "initial_cash": 100000,
        "fee_rate": 0.1,
        "preview_id": "preview-101",
        "approved_fingerprint": "fingerprint-101",
        "portfolio": {
            "symbols": ["BTC/USDT", "ETH/USDT"],
            "max_open_trades": 2,
            "position_size_pct": 25,
            "stake_mode": "fixed",
        },
        "research": {
            "slippage_bps": 5,
            "funding_rate_daily": 0,
            "in_sample_ratio": 70,
            "optimize_metric": "sharpe",
            "optimize_trials": 12,
            "rolling_windows": 3,
        },
    }


def make_paper_start_payload() -> dict[str, Any]:
    payload = make_backtest_start_payload()
    payload.pop("days")
    payload.pop("research")
    return payload


def make_template_payload() -> dict[str, Any]:
    return {
        "key": "trend_following_v2",  # gitleaks:allow
        "name": "Trend Following",
        "category": "trend",
        "description": "Template",
        "indicator_keys": ["ema_fast"],
        "default_config": make_strategy_config(),
        "default_parameter_space": {"ema_fast.period": [9, 12, 20]},
    }


def make_indicator_payload() -> dict[str, Any]:
    return {
        "key": "ema_fast",
        "name": "EMA Fast",
        "engine_key": "builtin.ema",
        "description": "Fast EMA",
        "params": [
            {
                "key": "period",
                "label": "Period",
                "type": "int",
                "default": 12,
                "min": 1,
                "max": 200,
                "step": 1,
            }
        ],
    }


def make_factor_execution_payload() -> dict[str, Any]:
    return {
        "initial_cash": 100000,
        "fee_rate": 0.1,
        "position_size_pct": 25,
        "stake_mode": "fixed",
        "entry_threshold": 0.8,
        "exit_threshold": 0.2,
        "stoploss_pct": -0.08,
        "takeprofit_pct": 0.16,
        "max_hold_bars": 20,
    }


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "expected"),
    [
        ("get", "/health", {}, lambda data: data["status"] == "healthy"),
        ("get", "/api/v1/status", {}, lambda data: data["framework"] == "FastAPI"),
        ("get", "/api/v1/config", {}, lambda data: "exchange" in data),
        ("get", "/api/v1/currencies", {}, lambda data: data["rates"]["CNY"] == 7.2 and data["supported"][0]["code"] == "USD"),
        ("get", "/api/v1/llm-config", {}, lambda data: "deepseek" in [item["id"] for item in data["presets"]] and "apiKeyPreview" in data),
        ("get", "/api/v1/fred-api-config", {}, lambda data: "apiKeyPreview" in data and data["source"] == "unset"),
        ("get", "/api/v1/realtime", {"params": {"symbol": "BTC/USDT"}}, lambda data: data["symbol"] == "BTC/USDT"),
        ("get", "/api/v1/price/current", {"params": {"symbol": "BTC/USDT"}}, lambda data: data["current_price"] == 68000.0),
        ("get", "/api/v1/price/current/batch", {"params": [("symbols", "BTC/USDT"), ("symbols", "ETH/USDT")]}, lambda data: len(data["items"]) == 2 and data["items"][0]["source"] == "websocket_snapshot"),
        ("get", "/api/v1/history", {"params": {"symbol": "BTC/USDT", "timeframe": "1h", "end_ts": 1710007200000}}, lambda data: data["symbol"] == "BTC/USDT" and len(data["items"]) == 3),
        ("get", "/api/v1/full_history", {"params": {"symbol": "BTC/USDT", "timeframe": "1d", "start_date": "2025-01-01"}}, lambda data: data["timeframe"] == "1d" and len(data["items"]) == 3),
        ("get", "/api/v1/indicators", {}, lambda data: data[0]["indicator_id"] == "FEAR_GREED"),
        ("get", "/api/v1/indicators/dli", {}, lambda data: data["score"] == 28 and data["components"][0]["indicator_id"] == "FED_BALANCE"),
        ("get", "/api/v1/funding-rate/current", {"params": {"symbol": "BTCUSDT"}}, lambda data: data["symbol"] == "BTCUSDT"),
        ("get", "/api/v1/binance/market/page", {}, lambda data: data["monitor"]["summary"]["focus_count"] == 1 and data["monitor"]["items"][0]["verdict"] == "优先关注"),
        ("post", "/api/v1/funding-rate/sync", {"params": {"symbol": "BTCUSDT", "start_date": "2025-01-01"}}, lambda data: data["inserted"] == 50),
        ("get", "/api/v1/funding-rate/history", {"params": {"symbol": "BTCUSDT"}}, lambda data: data["count"] == 1),
        ("get", "/api/v1/technical-metrics", {"params": {"symbol": "BTC/USDT"}}, lambda data: data["sample_size"] == 120),
        ("get", "/api/v1/trade-setup", {"params": {"symbol": "BTC/USDT", "timeframe": "1h"}}, lambda data: data["setup"]["side"] == "long"),
        ("post", "/api/v1/tools/dca_simulate", {"json": {"symbol": "BTC/USDT", "amount": 100}}, lambda data: data["profit_pct"] == 23.33),
        ("post", "/api/v1/tools/compare_pairs", {"json": {"symbol_a": "BTC", "symbol_b": "ETH", "days": 30, "timeframe": "1d"}}, lambda data: data["relative_strength"] == 1.12),
        ("get", "/api/v1/backtest/strategies", {}, lambda data: data[0]["key"] == "ema_rsi_macd"),
        ("get", "/api/v1/backtest/templates", {}, lambda data: data[0]["template"] == "trend_following"),
        ("get", "/api/v1/backtest/editor-contract", {}, lambda data: data["blank_group"]["node_type"] == "group"),
        ("get", "/api/v1/backtest/indicators", {}, lambda data: data[0]["key"] == "ema_fast"),
        ("get", "/api/v1/backtest/indicator-engines", {}, lambda data: data[0]["engine"] == "builtin.ema"),
        ("post", "/api/v1/backtest/101/evolve", {"json": {"dry_run": True}}, lambda data: data["defects"][0]["key"] == "negative_expectancy" and data["created"] is False),
        ("get", "/api/v1/backtest/list", {}, lambda data: data[0]["id"] == 101),
        ("get", "/api/v1/backtest/101", {}, lambda data: data["pagination"]["total"] == 1),
        ("get", "/api/v1/paper/list", {}, lambda data: data[0]["metadata"]["execution_mode"] == "paper_live"),
        ("get", "/api/v1/paper/202", {}, lambda data: data["id"] == 202),
        ("get", "/api/v1/factor-research/catalog", {}, lambda data: data["factors"][0]["factor_id"] == "fear_greed"),
        ("post", "/api/v1/factor-research/analyze", {"json": {"symbol": "BTC/USDT", "timeframe": "1d", "days": 365, "horizon_bars": 3, "max_lag_bars": 7, "categories": ["sentiment"], "factor_ids": ["fear_greed"]}}, lambda data: data["run_id"] == 301),
        ("get", "/api/v1/factor-research/runs", {}, lambda data: data[0]["id"] == 301),
        ("get", "/api/v1/factor-research/runs/301", {}, lambda data: data["details"][0]["factor_id"] == "fear_greed"),
    ],
)
def test_read_api_contracts(api_harness, method, path, kwargs, expected):
    response = getattr(api_harness["client"], method)(path, **kwargs)

    assert response.status_code == 200
    assert expected(response.json())


def test_full_history_uses_service_level_cache_write(api_harness):
    response = api_harness["client"].get(
        "/api/v1/full_history",
        params={"symbol": "BTC/USDT", "timeframe": "1d", "start_date": "2025-01-01"},
    )

    assert response.status_code == 200
    assert api_harness["market_query_app"].full_history_used_external_persist_callback is False


def test_backtest_mutation_routes_normalize_contracts(api_harness):
    client = api_harness["client"]

    preview_response = client.post("/api/v1/backtest/preview", json=make_backtest_start_payload())
    start_response = client.post("/api/v1/backtest/start", json=make_backtest_start_payload())
    paper_response = client.post("/api/v1/paper/start", json=make_paper_start_payload())
    template_response = client.post("/api/v1/backtest/templates", json=make_template_payload())
    indicator_response = client.post("/api/v1/backtest/indicators", json=make_indicator_payload())
    strategy_response = client.post(
        "/api/v1/backtest/strategies",
        json={
            "key": "ema_rsi_macd",
            "name": "EMA RSI MACD v2",
            "template": "trend_following",
            "category": "trend",
            "description": "Version 2",
            "config": make_strategy_config(),
            "parameter_space": {"ema_fast.period": [9, 12, 20]},
            "notes": "Stable release",
            "make_default": True,
        },
    )
    evolve_response = client.post(
        "/api/v1/backtest/101/evolve",
        json={"version_name": "EMA RSI MACD evolved", "make_default": False},
    )

    assert preview_response.status_code == 200
    assert start_response.status_code == 200
    assert paper_response.status_code == 200
    assert template_response.status_code == 200
    assert indicator_response.status_code == 200
    assert strategy_response.status_code == 200
    assert evolve_response.status_code == 200

    preview_command = api_harness["backtest_command"].received_commands["preview_backtest"]
    start_command = api_harness["backtest_command"].received_commands["start_backtest"]
    paper_command = api_harness["backtest_command"].received_commands["start_paper_run"]
    template_command = api_harness["backtest_command"].received_commands["create_template"]
    indicator_command = api_harness["backtest_command"].received_commands["create_indicator"]
    strategy_command = api_harness["backtest_command"].received_commands["create_strategy_version"]
    evolve_command = api_harness["backtest_command"].received_commands["evolve_strategy_from_backtest"]

    assert preview_command.portfolio.symbols == ["BTC/USDT", "ETH/USDT"]
    assert start_command.portfolio.symbols == ["BTC/USDT", "ETH/USDT"]
    assert start_command.preview_id == "preview-101"
    assert start_command.research.optimize_metric == "sharpe"
    assert paper_command.portfolio.max_open_trades == 2
    assert template_command.key == "trend_following_v2"  # gitleaks:allow
    assert indicator_command.engine_key == "builtin.ema"
    assert strategy_command.make_default is True
    assert evolve_command.backtest_id == 101
    assert evolve_command.make_default is False


def test_backtest_delete_and_stop_routes(api_harness):
    client = api_harness["client"]

    stop_response = client.post("/api/v1/paper/202/stop")
    delete_backtest_response = client.delete("/api/v1/backtest/101")
    delete_paper_response = client.delete("/api/v1/paper/202")

    assert stop_response.status_code == 200
    assert delete_backtest_response.status_code == 200
    assert delete_paper_response.status_code == 200
    assert api_harness["backtest_command"].received_commands["stop_paper_run"] == 202
    assert api_harness["backtest_command"].received_commands["delete_backtest"] == 101
    assert api_harness["backtest_command"].received_commands["delete_paper_run"] == 202


def test_factor_execution_routes_forward_full_payload(api_harness):
    client = api_harness["client"]

    backtest_response = client.post(
        "/api/v1/factor-research/runs/301/backtest",
        json=make_factor_execution_payload(),
    )
    paper_response = client.post(
        "/api/v1/factor-research/runs/301/paper",
        json=make_factor_execution_payload(),
    )

    assert backtest_response.status_code == 200
    assert paper_response.status_code == 200
    assert api_harness["factor_execution"].calls[0].research_run_id == 301
    assert api_harness["factor_execution"].calls[0].entry_threshold == 0.8
    assert api_harness["factor_paper"].calls[0].max_hold_bars == 20


def test_value_errors_are_mapped_to_bad_request(api_harness, monkeypatch):
    async def fail_market(**kwargs):
        raise ValueError("bad market input")

    async def fail_factor(**kwargs):
        raise ValueError("bad factor input")

    monkeypatch.setattr(api_harness["market_query_app"], "get_realtime", fail_market)
    monkeypatch.setattr(api_harness["factor_research"], "analyze_async", fail_factor)

    realtime_response = api_harness["client"].get("/api/v1/realtime", params={"symbol": "BTC/USDT"})
    factor_response = api_harness["client"].post(
        "/api/v1/factor-research/analyze",
        json={"symbol": "BTC/USDT", "timeframe": "1d", "days": 365, "horizon_bars": 3, "max_lag_bars": 7},
    )

    assert realtime_response.status_code == 400
    assert factor_response.status_code == 400


@pytest.mark.asyncio
async def test_full_history_rejects_invalid_start_date():
    service = MarketQueryAppService(
        market_data_service=object(),
        realtime_service=object(),
    )

    with pytest.raises(ValueError, match="start_date 必须是 YYYY-MM-DD"):
        await service.get_full_history(
            symbol="BTC/USDT",
            timeframe="1d",
            start_date="2025/01/01",
        )


def test_backtest_detail_returns_not_found_when_service_returns_none(api_harness, monkeypatch):
    async def missing_run(backtest_id: int, page: int, page_size: int):
        return None

    monkeypatch.setattr(api_harness["backtest_query"], "get_run", missing_run)

    response = api_harness["client"].get("/api/v1/backtest/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "回测记录不存在"
