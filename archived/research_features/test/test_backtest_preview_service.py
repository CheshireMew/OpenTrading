from __future__ import annotations

from datetime import datetime

import pytest

from app.application.backtest.preview_service import BacktestPreviewService
from app.application.backtest.preview_artifact_store import StoredStrategyPreview
from app.contracts.backtest import (
    BacktestPortfolioConfig,
    BacktestPreviewCommand,
    BacktestResearchConfig,
    StrategyVersionRecord,
)
from app.domain.backtest.strategy_rule_tree import build_condition, build_group
from app.domain.backtest.strategy_catalog import get_builtin_strategy_definitions
from app.domain.backtest.strategy_support import normalize_strategy_version_config_model
from app.services.backtest.strategy_runtime import StrategyRuntime
from app.services.market.kline_range_loader import OhlcvRangeResult


class _MarketDataServiceStub:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows

    def load_ohlcv_range(self, *_args, **_kwargs) -> OhlcvRangeResult:
        return OhlcvRangeResult(self.rows, [])


class _PreviewArtifactStoreStub:
    def __init__(self) -> None:
        self.artifacts: dict[str, StoredStrategyPreview] = {}

    def save(self, preview: StoredStrategyPreview) -> None:
        self.artifacts[preview.preview_id] = preview

    def get(self, preview_id: str) -> StoredStrategyPreview | None:
        return self.artifacts.get(preview_id)


def _preview_service() -> BacktestPreviewService:
    return BacktestPreviewService(
        market_data_service=_MarketDataServiceStub(_rows()),
        strategy_runtime=StrategyRuntime(),
        artifact_store=_PreviewArtifactStoreStub(),
    )


def _rows() -> list[list[float]]:
    base = 1_710_000_000_000
    day_ms = 86_400_000
    rows: list[list[float]] = []
    for index in range(12):
        close = 98.0 + index
        rows.append([base + index * day_ms, close - 1, close + 1, close - 2, close, 1000 + index])
    return rows


def _strategy() -> StrategyVersionRecord:
    config = {
        "indicators": {},
        "execution": {"market_type": "spot", "direction": "long_only"},
        "regime_priority": ["trend", "range"],
        "trend": {
            "id": "trend",
            "label": "Trend",
            "enabled": True,
            "regime": build_group("trend_regime", "趋势状态", "and", []),
            "long_entry": build_group(
                "trend_long_entry",
                "趋势做多入场",
                "and",
                [
                    build_condition(
                        "close_gt_105",
                        "收盘价高于 105",
                        {"kind": "price", "field": "close"},
                        "gt",
                        {"kind": "value", "value": 105},
                    )
                ],
            ),
            "long_exit": build_group("trend_long_exit", "趋势做多离场", "or", [], enabled=False),
            "short_entry": build_group("trend_short_entry", "趋势做空入场", "and", [], enabled=False),
            "short_exit": build_group("trend_short_exit", "趋势做空离场", "or", [], enabled=False),
        },
        "range": {
            "id": "range",
            "label": "Range",
            "enabled": False,
            "regime": build_group("range_regime", "区间状态", "and", []),
            "long_entry": build_group("range_long_entry", "区间做多入场", "and", []),
            "long_exit": build_group("range_long_exit", "区间做多离场", "or", []),
            "short_entry": build_group("range_short_entry", "区间做空入场", "and", [], enabled=False),
            "short_exit": build_group("range_short_exit", "区间做空离场", "or", [], enabled=False),
        },
    }
    return StrategyVersionRecord(
        strategy_key="preview_demo",
        strategy_name="Preview Demo",
        version=1,
        template="ema_rsi_macd",
        config=normalize_strategy_version_config_model("ema_rsi_macd", config).model_dump(),
    )


def _strategy_with_always_on_exit() -> StrategyVersionRecord:
    config = _strategy().config
    config["trend"]["long_exit"] = build_group(
        "trend_long_exit",
        "趋势做多离场",
        "or",
        [
            build_condition(
                "close_gt_zero",
                "收盘价高于 0",
                {"kind": "price", "field": "close"},
                "gt",
                {"kind": "value", "value": 0},
            )
        ],
    )
    return StrategyVersionRecord(
        strategy_key="preview_demo",
        strategy_name="Preview Demo",
        version=1,
        template="ema_rsi_macd",
        config=config,
    )


def _command(symbols: list[str] | None = None) -> BacktestPreviewCommand:
    return BacktestPreviewCommand(
        strategy_key="preview_demo",
        strategy_version=1,
        timeframe="1d",
        start_date=datetime(2024, 3, 1),
        end_date=datetime(2024, 3, 12),
        initial_cash=10_000,
        fee_rate=0.1,
        portfolio=BacktestPortfolioConfig(
            symbols=symbols or ["BTC/USDT"],
            max_open_trades=1,
            position_size_pct=20,
            stake_mode="fixed",
        ),
        research=BacktestResearchConfig(optimize_trials=0, rolling_windows=0),
    )


def test_preview_service_builds_candle_signal_artifact():
    service = _preview_service()

    artifact = service.build_preview(strategy=_strategy(), command=_command())

    assert artifact["symbols"] == ["BTC/USDT"]
    assert artifact["candles"]["BTC/USDT"]
    assert artifact["fingerprint"]
    markers = artifact["markers"]["BTC/USDT"]
    assert [marker["kind"] for marker in markers] == ["long_entry"]


def test_preview_service_marks_executable_position_events_only():
    service = _preview_service()

    artifact = service.build_preview(strategy=_strategy_with_always_on_exit(), command=_command())

    markers = artifact["markers"]["BTC/USDT"]
    assert [marker["kind"] for marker in markers[:2]] == ["long_entry", "long_exit"]
    assert markers[0]["time"] < markers[1]["time"]


def test_preview_approval_rejects_parameter_drift():
    service = _preview_service()
    strategy = _strategy()
    artifact = service.build_preview(strategy=strategy, command=_command())

    service.require_approved(
        preview_id=artifact["preview_id"],
        approved_fingerprint=artifact["fingerprint"],
        strategy=strategy,
        command=_command(),
    )

    with pytest.raises(ValueError, match="不一致"):
        service.require_approved(
            preview_id=artifact["preview_id"],
            approved_fingerprint=artifact["fingerprint"],
            strategy=strategy,
            command=_command(["ETH/USDT"]),
        )


def test_ema_rsi_macd_default_long_exit_uses_rsi_breakdown_not_always_on_threshold():
    definition = next(item for item in get_builtin_strategy_definitions() if item["key"] == "ema_rsi_macd")
    config = definition["versions"][0]["config"]
    rsi_exit = next(
        child
        for child in config["trend"]["long_exit"]["children"]
        if child["id"] == "exit_rsi_min"
    )

    assert rsi_exit["operator"] == "lt"
    assert rsi_exit["label"] == "RSI 低于离场阈值"
