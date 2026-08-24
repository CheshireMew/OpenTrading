from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

import pandas as pd

from app.application.backtest.preview_artifact_store import StoredStrategyPreview
from app.contracts.backtest import BacktestPreviewCommand, StrategyVersionRecord
from app.contracts.market_history import build_market_history_coverage_payload, build_ohlcv_point_payloads

PreviewDiagnosticSeverity = Literal["info", "warning", "critical"]


class BacktestPreviewPayloadBuilder:
    def build_preview(
        self,
        *,
        strategy: StrategyVersionRecord,
        command: BacktestPreviewCommand,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        selected_config: Any,
        symbol_frames: dict[str, pd.DataFrame],
        symbol_rows: dict[str, list[list[float]]],
        symbol_missing_ranges: dict[str, Any],
    ) -> StoredStrategyPreview:
        candles_by_symbol: dict[str, list[dict[str, Any]]] = {}
        markers_by_symbol: dict[str, list[dict[str, Any]]] = {}
        indicator_series_by_symbol: dict[str, list[dict[str, Any]]] = {}
        coverage_by_symbol: dict[str, dict[str, Any]] = {}
        diagnostics: list[dict[str, Any]] = []

        for symbol in symbols:
            rows = symbol_rows[symbol]
            frame = symbol_frames[symbol]
            candles_by_symbol[symbol] = build_ohlcv_point_payloads(rows)
            coverage_by_symbol[symbol] = build_market_history_coverage_payload(symbol_missing_ranges[symbol])
            if symbol_missing_ranges[symbol]:
                diagnostics.append(
                    self._diagnostic(
                        "critical",
                        f"{symbol} K线历史不完整",
                        "预览存在缺口，确认前应补齐数据，否则信号和回测都不可信。",
                    )
                )
            markers = self._build_markers(symbol=symbol, frame=frame)
            markers_by_symbol[symbol] = markers
            indicator_series_by_symbol[symbol] = self._build_indicator_series(
                symbol=symbol,
                frame=frame,
                indicators=selected_config.indicators,
            )
            diagnostics.extend(self._build_symbol_diagnostics(symbol=symbol, rows=rows, markers=markers))

        command_payload = command_payload_for_preview(
            strategy=strategy,
            command=command,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )
        fingerprint = self._fingerprint(
            {
                "command": command_payload,
                "candles": candles_by_symbol,
                "markers": markers_by_symbol,
                "indicator_series": indicator_series_by_symbol,
            }
        )
        preview_id = uuid4().hex
        artifact = {
            "preview_id": preview_id,
            "fingerprint": fingerprint,
            "strategy_key": strategy.strategy_key,
            "strategy_name": strategy.strategy_name,
            "strategy_version": strategy.version,
            "strategy_template": strategy.template,
            "timeframe": command.timeframe,
            "symbols": symbols,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "candles": candles_by_symbol,
            "markers": markers_by_symbol,
            "indicator_series": indicator_series_by_symbol,
            "coverage": coverage_by_symbol,
            "diagnostics": diagnostics,
        }
        return StoredStrategyPreview(
            preview_id=preview_id,
            fingerprint=fingerprint,
            command_payload=command_payload,
            artifact=artifact,
        )

    def _build_markers(self, *, symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
        if frame.empty:
            return []
        markers: list[dict[str, Any]] = []
        active_side: str | None = None
        for _, row in frame.iterrows():
            timestamp = self._timestamp_ms(row)
            price = self._float_or_none(row.get("close"))
            if timestamp is None or price is None:
                continue
            row_markers: list[tuple[str, str, str]] = []
            closed_this_bar = False
            if active_side == "long":
                if bool(row.get("long_exit_signal")):
                    row_markers.append(("long_exit", "long", "做多离场"))
                    active_side = None
                    closed_this_bar = True
            elif active_side == "short":
                if bool(row.get("short_exit_signal")):
                    row_markers.append(("short_exit", "short", "做空离场"))
                    active_side = None
                    closed_this_bar = True

            if active_side is None and not closed_this_bar:
                if bool(row.get("long_entry_signal")):
                    row_markers.append(("long_entry", "long", "做多入场"))
                    active_side = "long"
                elif bool(row.get("short_entry_signal")):
                    row_markers.append(("short_entry", "short", "做空入场"))
                    active_side = "short"

            for kind, side, label in row_markers:
                markers.append(self._marker_payload(symbol=symbol, row=row, timestamp=timestamp, price=price, kind=kind, side=side, label=label))
        return markers

    def _marker_payload(
        self,
        *,
        symbol: str,
        row: pd.Series,
        timestamp: int,
        price: float,
        kind: str,
        side: str,
        label: str,
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "time": int(timestamp),
            "price": price,
            "kind": kind,
            "side": side,
            "label": label,
            "active_regime": row.get("active_regime") or None,
            "indicators": self._row_indicator_values(row),
        }

    def _build_indicator_series(
        self,
        *,
        symbol: str,
        frame: pd.DataFrame,
        indicators: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if frame.empty:
            return []
        series: list[dict[str, Any]] = []
        for indicator_id, indicator in indicators.items():
            prefix = f"{indicator_id}__"
            output_columns = [str(column) for column in frame.columns if str(column).startswith(prefix)]
            for column in output_columns:
                output = column[len(prefix):]
                points = []
                for _, row in frame.iterrows():
                    value = self._float_or_none(row.get(column))
                    timestamp = self._timestamp_ms(row)
                    if value is None or timestamp is None:
                        continue
                    points.append({"time": int(timestamp), "value": value})
                if not points:
                    continue
                series.append(
                    {
                        "symbol": symbol,
                        "indicator_id": indicator_id,
                        "output": output,
                        "label": f"{getattr(indicator, 'label', None) or indicator_id} · {output}",
                        "points": points,
                    }
                )
        return series

    def _build_symbol_diagnostics(
        self,
        *,
        symbol: str,
        rows: list[list[float]],
        markers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        diagnostics: list[dict[str, Any]] = []
        if not rows:
            diagnostics.append(self._diagnostic("critical", f"{symbol} 没有K线数据", "无法生成策略预览。"))
            return diagnostics
        entry_count = sum(1 for marker in markers if str(marker["kind"]).endswith("entry"))
        if entry_count == 0:
            diagnostics.append(
                self._diagnostic(
                    "warning",
                    f"{symbol} 没有入场信号",
                    "请确认规则、周期和样本区间是否符合预期。",
                )
            )
        if entry_count > max(len(rows) * 0.2, 50):
            diagnostics.append(
                self._diagnostic(
                    "warning",
                    f"{symbol} 入场信号过密",
                    "信号数量相对K线过高，建议检查规则是否过宽。",
                )
            )
        return diagnostics

    def _diagnostic(
        self,
        severity: PreviewDiagnosticSeverity,
        title: str,
        message: str,
    ) -> dict[str, Any]:
        return {"severity": severity, "title": title, "message": message}

    def _row_indicator_values(self, row: pd.Series) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, value in row.items():
            key_text = str(key)
            if "__" not in key_text:
                continue
            coerced = self._float_or_none(value)
            if coerced is not None:
                values[key_text] = coerced
        return values

    def _timestamp_ms(self, row: pd.Series) -> int | None:
        value = row.get("timestamp")
        if value is not None and pd.notna(value):
            return int(value)
        date_value = row.get("date")
        if date_value is None or pd.isna(date_value):
            return None
        return int(pd.Timestamp(date_value).timestamp() * 1000)

    def _float_or_none(self, value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if result == result and result not in {float("inf"), float("-inf")} else None

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def command_payload_for_preview(
    *,
    strategy: StrategyVersionRecord,
    command: BacktestPreviewCommand,
    symbols: list[str],
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    return {
        "strategy_key": strategy.strategy_key,
        "strategy_version": strategy.version,
        "strategy_template": strategy.template,
        "timeframe": command.timeframe,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "initial_cash": float(command.initial_cash),
        "fee_rate": float(command.fee_rate),
        "symbols": symbols,
        "portfolio": command.portfolio.model_dump(mode="json"),
        "research": command.research.model_dump(mode="json"),
    }
