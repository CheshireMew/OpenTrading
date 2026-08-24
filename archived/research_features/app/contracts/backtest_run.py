from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.contracts.backtest import BacktestPortfolioConfig, BacktestResearchConfig, StrategyVersionRecord
from app.contracts.backtest_metadata import (
    BACKTEST_RUN_METADATA_ADAPTER,
    BacktestExecutionMetadata,
    BacktestPaperLiveState,
    BacktestRunMetadata,
    BacktestRunMetadataCommon,
    BacktestRuntimeState,
)


CURRENT_BACKTEST_RUN_SCHEMA_VERSION = 4

BACKTEST_EXECUTION_MODE = "backtest"
PAPER_LIVE_EXECUTION_MODE = "paper_live"
FREQTRADE_ENGINE = "Freqtrade"
PAPER_LIVE_ENGINE = "FreqtradePaper"
FACTOR_BLEND_ENGINE = "FactorBlend"
FACTOR_BLEND_PAPER_ENGINE = "FactorBlendPaper"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_STOPPED = "stopped"
RETENTION_ELIGIBLE_RUN_STATUSES = (RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_STOPPED)
_MISSING = object()


@dataclass(slots=True)
class StoredBacktestRun:
    id: int
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    status: str
    execution_mode: str
    engine: str
    metadata: BacktestRunMetadata


def build_portfolio_payload(portfolio: BacktestPortfolioConfig) -> dict[str, Any]:
    return portfolio.model_dump(mode="json")


def build_research_payload(research: BacktestResearchConfig) -> dict[str, Any]:
    return research.model_dump(mode="json")


def build_base_metadata(
    *,
    strategy: StrategyVersionRecord,
    symbols: list[str],
    initial_cash: float,
    fee_rate: float,
    portfolio_label: str,
    portfolio: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CURRENT_BACKTEST_RUN_SCHEMA_VERSION,
        "strategy_key": strategy.strategy_key,
        "strategy_name": strategy.strategy_name,
        "strategy_version": strategy.version,
        "strategy_template": strategy.template,
        "symbols": symbols,
        "portfolio_label": portfolio_label,
        "initial_cash": initial_cash,
        "fee_rate": fee_rate,
        "portfolio": portfolio,
    }


def build_backtest_metadata(
    *,
    strategy: StrategyVersionRecord,
    symbols: list[str],
    initial_cash: float,
    fee_rate: float,
    portfolio: BacktestPortfolioConfig,
    research: BacktestResearchConfig,
    preview_id: str | None = None,
    preview_fingerprint: str | None = None,
    preview_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        **build_base_metadata(
            strategy=strategy,
            symbols=symbols,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            portfolio_label=symbols[0] if len(symbols) == 1 else f"{len(symbols)} symbols",
            portfolio=build_portfolio_payload(portfolio),
        ),
        "execution_mode": BACKTEST_EXECUTION_MODE,
        "research": build_research_payload(research),
    }
    if preview_id and preview_fingerprint:
        artifact = dict(preview_artifact or {})
        payload["preview"] = {
            "id": preview_id,
            "fingerprint": preview_fingerprint,
            "strategy_key": artifact.get("strategy_key") or strategy.strategy_key,
            "strategy_version": artifact.get("strategy_version") or strategy.version,
            "timeframe": artifact.get("timeframe"),
            "symbols": list(artifact.get("symbols") or symbols),
            "markers": dict(artifact.get("markers") or {}),
            "diagnostics": list(artifact.get("diagnostics") or []),
        }
    return make_json_safe(payload)


def parse_run_metadata(metadata: BaseModel | dict[str, Any] | None) -> BacktestRunMetadata:
    payload = metadata.model_dump() if isinstance(metadata, BaseModel) else dict(metadata or {})
    return validate_backtest_run_metadata(payload)


def serialize_run_metadata(metadata: BaseModel | dict[str, Any] | None, *, execution_mode: str, engine: str) -> dict[str, Any]:
    payload = _dump_model(metadata) if metadata else {}
    payload["execution_mode"] = execution_mode
    payload["engine"] = engine
    return _validate_run_metadata(payload)


def build_completed_run_metadata(
    metadata: BaseModel | dict[str, Any] | None,
    *,
    result_metadata: BaseModel | dict[str, Any] | None,
    report: BaseModel | dict[str, Any],
) -> dict[str, Any]:
    payload = parse_run_metadata(metadata).model_dump()
    if result_metadata:
        result_payload = _dump_model(result_metadata)
        if result_payload.get("preview") is None and payload.get("preview") is not None:
            result_payload.pop("preview", None)
        payload.update(result_payload)
    payload["schema_version"] = CURRENT_BACKTEST_RUN_SCHEMA_VERSION
    payload["report"] = _dump_model(report)
    return _validate_run_metadata(payload)


def build_failed_run_metadata(
    metadata: BaseModel | dict[str, Any] | None,
    *,
    error: str,
) -> dict[str, Any]:
    payload = parse_run_metadata(metadata).model_dump()
    payload["schema_version"] = CURRENT_BACKTEST_RUN_SCHEMA_VERSION
    payload["error"] = error
    return _validate_run_metadata(payload)


def build_paper_metadata(
    *,
    strategy: StrategyVersionRecord,
    symbols: list[str],
    initial_cash: float,
    fee_rate: float,
    portfolio: BacktestPortfolioConfig,
    runtime_state: dict[str, Any],
    paper_live: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    last_updated = (paper_live or {}).get("last_updated")
    if not last_updated:
        raise ValueError("paper_live.last_updated 不能为空")

    metadata = {
        **build_base_metadata(
            strategy=strategy,
            symbols=symbols,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            portfolio_label=symbols[0] if len(symbols) == 1 else f"{len(symbols)} symbols",
            portfolio=build_portfolio_payload(portfolio),
        ),
        "execution_mode": PAPER_LIVE_EXECUTION_MODE,
    }
    stop_reason = paper_live["stop_reason"] if isinstance(paper_live, dict) and "stop_reason" in paper_live else _MISSING
    return update_paper_metadata(
        metadata,
        runtime_state=runtime_state,
        last_updated=last_updated,
        report=report,
        stop_reason=stop_reason,
    )


def ensure_paper_runtime_state(runtime_state: dict[str, Any], *, symbols: list[str]) -> dict[str, Any]:
    if not isinstance(runtime_state, dict):
        raise ValueError("paper runtime_state 必须是字典")

    normalized = {
        key: value
        for key, value in runtime_state.items()
        if key not in {"cash_balance", "last_processed", "last_synced_end", "positions", "held_bars"}
    }

    normalized["cash_balance"] = float(runtime_state.get("cash_balance", 0.0) or 0.0)
    normalized["last_processed"] = _normalize_last_processed_map(runtime_state.get("last_processed"), symbols=symbols)
    normalized["last_synced_end"] = _normalize_optional_timestamp_ms(runtime_state.get("last_synced_end"))
    normalized["positions"] = _normalize_paper_positions(runtime_state.get("positions"), symbols=symbols)
    normalized["held_bars"] = int(runtime_state.get("held_bars", 0) or 0)
    return BacktestRuntimeState.model_validate(make_json_safe(normalized)).model_dump()


def update_paper_metadata(
    metadata: BaseModel | dict[str, Any] | None,
    *,
    runtime_state: dict[str, Any],
    last_updated: str,
    report: BaseModel | dict[str, Any] | object = _MISSING,
    stop_reason: str | None | object = _MISSING,
) -> dict[str, Any]:
    payload = parse_run_metadata(metadata).model_dump()
    payload["execution_mode"] = PAPER_LIVE_EXECUTION_MODE
    symbols = [str(symbol) for symbol in (payload.get("symbols") or []) if symbol]
    normalized_runtime_state = ensure_paper_runtime_state(runtime_state, symbols=symbols)
    existing_paper_live = dict(payload.get("paper_live") or {}) if isinstance(payload.get("paper_live"), dict) else {}

    payload["schema_version"] = CURRENT_BACKTEST_RUN_SCHEMA_VERSION
    payload["runtime_state"] = normalized_runtime_state
    payload["paper_live"] = _build_paper_live_state(
        existing_paper_live,
        runtime_state=normalized_runtime_state,
        last_updated=last_updated,
        stop_reason=stop_reason,
    )
    if report is not _MISSING:
        payload["report"] = _dump_model(report)
    return _validate_run_metadata(payload)


def _build_paper_live_state(
    current_paper_live: dict[str, Any],
    *,
    runtime_state: dict[str, Any],
    last_updated: str,
    stop_reason: str | None | object,
) -> dict[str, Any]:
    positions = list((runtime_state.get("positions") or {}).values())
    paper_live = {
        key: value
        for key, value in current_paper_live.items()
        if key not in {"cash_balance", "open_positions", "positions", "last_updated", "stop_reason"}
    }
    paper_live["cash_balance"] = float(runtime_state.get("cash_balance", 0.0) or 0.0)
    paper_live["open_positions"] = len(positions)
    paper_live["positions"] = positions
    paper_live["last_updated"] = last_updated
    if stop_reason is not _MISSING:
        paper_live["stop_reason"] = stop_reason
    elif "stop_reason" in current_paper_live:
        paper_live["stop_reason"] = current_paper_live["stop_reason"]
    return BacktestPaperLiveState.model_validate(make_json_safe(paper_live)).model_dump()


def _normalize_last_processed_map(value: Any, *, symbols: list[str]) -> dict[str, int | None]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("paper runtime_state.last_processed 必须是按 symbol 存储的字典")

    normalized: dict[str, int | None] = {}
    known_symbols = {str(symbol) for symbol in symbols if symbol}
    for symbol, timestamp in value.items():
        symbol_key = str(symbol).strip()
        if not symbol_key:
            continue
        if known_symbols and symbol_key not in known_symbols:
            raise ValueError(f"paper runtime_state.last_processed 存在未知 symbol: {symbol_key}")
        normalized[symbol_key] = _normalize_optional_timestamp_ms(timestamp)
    return normalized


def _normalize_paper_positions(value: Any, *, symbols: list[str]) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("paper runtime_state.positions 必须是按 symbol 存储的字典")

    normalized: dict[str, dict[str, Any]] = {}
    known_symbols = {str(symbol) for symbol in symbols if symbol}
    for symbol, payload in value.items():
        symbol_key = str(symbol).strip()
        if not symbol_key:
            continue
        if known_symbols and symbol_key not in known_symbols:
            raise ValueError(f"paper runtime_state.positions 存在未知 symbol: {symbol_key}")
        normalized[symbol_key] = _normalize_paper_position_payload(payload, symbol_hint=symbol_key)
    return normalized


def _normalize_paper_position_payload(payload: Any, *, symbol_hint: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"paper position {symbol_hint} 必须是字典")

    missing_keys = [key for key in ("opened_at", "entry_price", "remaining_amount", "remaining_cost") if payload.get(key) is None]
    if missing_keys:
        raise ValueError(f"paper position {symbol_hint} 缺少字段: {', '.join(missing_keys)}")

    entry_price = float(payload.get("entry_price", 0.0) or 0.0)
    side = str(payload.get("side") or "long").strip().lower()
    if side not in {"long", "short"}:
        side = "long"
    normalized = {
        "symbol": str(payload.get("symbol") or symbol_hint),
        "side": side,
        "opened_at": payload["opened_at"],
        "entry_price": entry_price,
        "remaining_amount": float(payload["remaining_amount"]),
        "remaining_cost": float(payload["remaining_cost"]),
        "highest_price": float(payload.get("highest_price", entry_price) or entry_price),
        "lowest_price": float(payload.get("lowest_price", entry_price) or entry_price),
        "last_price": float(payload.get("last_price", entry_price) or entry_price),
        "taken_partial_ids": list(payload.get("taken_partial_ids") or []),
    }
    # entry_score belongs to factor paper positions; empty values must stay empty,
    # otherwise normal paper positions get a fake score of 0.0 on the next save.
    if payload.get("entry_score") not in (None, ""):
        normalized["entry_score"] = float(payload.get("entry_score", 0.0) or 0.0)
    return normalized


def _normalize_optional_timestamp_ms(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"paper last_processed 无法转换为毫秒时间戳: {value}") from exc


def make_json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return make_json_safe(value.model_dump())
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _dump_model(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return value.model_dump() if isinstance(value, BaseModel) else dict(value)


def validate_backtest_run_metadata(payload: dict[str, Any]) -> BacktestRunMetadata:
    safe_payload = make_json_safe(payload)
    if not safe_payload.get("execution_mode"):
        safe_payload["execution_mode"] = _infer_execution_mode(safe_payload)
    return BACKTEST_RUN_METADATA_ADAPTER.validate_python(safe_payload)


def _infer_execution_mode(payload: dict[str, Any]) -> str:
    if payload.get("runtime_state") is not None or payload.get("paper_live") is not None:
        return PAPER_LIVE_EXECUTION_MODE
    return BACKTEST_EXECUTION_MODE


def _validate_run_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return validate_backtest_run_metadata(payload).model_dump()
