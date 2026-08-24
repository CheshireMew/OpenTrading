from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from freqtrade.data.history.datahandlers.jsondatahandler import JsonDataHandler
from freqtrade.enums import CandleType

from app.domain.market.timeframes import timeframe_to_timedelta
from app.services.market.market_data_service import MarketDataService
from config import settings


class FreqtradeDataExporter:
    def __init__(
        self,
        *,
        workspace_root: Path,
        market_data_service: MarketDataService,
    ) -> None:
        self.market_data_service = market_data_service
        self.shared_data_dir = workspace_root / "_shared_data" / settings.EXCHANGE_ID
        self.shared_manifest_path = workspace_root / "_shared_data" / "coverage.json"
        self.shared_lock_path = workspace_root / "_shared_data" / "coverage.lock"

    def export_history(
        self,
        *,
        data_symbols: list[str],
        execution_symbols: list[str],
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        warmup_bars: int,
        market_type: str,
    ) -> int:
        lock_file = self._acquire_shared_data_lock()
        try:
            return self._export_history_locked(
                data_symbols=data_symbols,
                execution_symbols=execution_symbols,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                warmup_bars=warmup_bars,
                market_type=market_type,
            )
        finally:
            self._release_shared_data_lock(lock_file)

    def _export_history_locked(
        self,
        *,
        data_symbols: list[str],
        execution_symbols: list[str],
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        warmup_bars: int,
        market_type: str,
    ) -> int:
        total_candles = 0
        self.shared_data_dir.mkdir(parents=True, exist_ok=True)
        handler = JsonDataHandler(self.shared_data_dir)
        manifest = self._load_shared_coverage()
        manifest_changed = False
        warmup_start = start_date - (timeframe_to_timedelta(timeframe) * warmup_bars)
        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)
        request_start_ms = int(warmup_start.timestamp() * 1000)
        for data_symbol, execution_symbol in zip(data_symbols, execution_symbols, strict=True):
            candle_type = CandleType.FUTURES if market_type == "futures" else CandleType.SPOT
            manifest_key = self._shared_coverage_key(
                execution_symbol=execution_symbol,
                timeframe=timeframe,
                candle_type=candle_type,
            )
            coverage = manifest.get(manifest_key) or {}
            if self._needs_history_refresh(
                coverage=coverage,
                data_symbol=data_symbol,
                start_ms=request_start_ms,
                end_ms=end_ms,
            ):
                range_result = self.market_data_service.load_ohlcv_range(
                    data_symbol, timeframe, warmup_start, end_date
                )
                rows = range_result.require_complete(symbol=data_symbol, timeframe=timeframe)
                if not rows:
                    raise RuntimeError(f"没有可用于 Freqtrade 回测的历史数据: {data_symbol} {timeframe}")
                frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
                frame["date"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
                frame = frame.loc[:, ["date", "open", "high", "low", "close", "volume"]]
                handler.ohlcv_store(execution_symbol, timeframe, frame, candle_type)
                manifest[manifest_key] = {
                    "data_symbol": data_symbol,
                    "start_ms": int(frame["date"].iloc[0].value // 1_000_000),
                    "end_ms": int(frame["date"].iloc[-1].value // 1_000_000),
                }
                manifest_changed = True
            frame = handler._ohlcv_load(execution_symbol, timeframe, None, candle_type)
            if frame.empty:
                raise RuntimeError(f"共享回测数据不可用: {execution_symbol} {timeframe}")
            total_candles += int(
                frame["date"]
                .astype("int64")
                .floordiv(1_000_000)
                .between(start_ms, end_ms)
                .sum()
            )
        if manifest_changed:
            self._save_shared_coverage(manifest)
        return total_candles

    def _acquire_shared_data_lock(self):
        self.shared_lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.shared_lock_path.open("a+b")
        lock_file.seek(0)
        if lock_file.read(1) == b"":
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return lock_file

    @staticmethod
    def _release_shared_data_lock(lock_file) -> None:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

    @staticmethod
    def _shared_coverage_key(
        *,
        execution_symbol: str,
        timeframe: str,
        candle_type: CandleType,
    ) -> str:
        return f"{execution_symbol}|{timeframe}|{candle_type.value}"

    @staticmethod
    def _needs_history_refresh(
        *,
        coverage: dict[str, Any],
        data_symbol: str,
        start_ms: int,
        end_ms: int,
    ) -> bool:
        if not coverage:
            return True
        if str(coverage.get("data_symbol") or "") != data_symbol:
            return True
        if int(coverage.get("start_ms") or start_ms + 1) > start_ms:
            return True
        if int(coverage.get("end_ms") or end_ms - 1) < end_ms:
            return True
        return False

    def _load_shared_coverage(self) -> dict[str, dict[str, Any]]:
        if not self.shared_manifest_path.exists():
            return {}
        try:
            payload = json.loads(self.shared_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): value for key, value in payload.items() if isinstance(value, dict)}

    def _save_shared_coverage(self, coverage: dict[str, dict[str, Any]]) -> None:
        self.shared_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.shared_manifest_path.write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
