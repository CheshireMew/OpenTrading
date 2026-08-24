from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.market.constants import timeframe_to_milliseconds
from app.services.market.symbol_catalog import resolve_market_asset
from app.services.market.market_data_service import MarketDataService
from app.services.market.index_data_service import IndexDataService
from config import settings
from utils.logger import logger


class PairCompareService:
    def __init__(
        self,
        market_data_service: MarketDataService | None = None,
        index_data_service: IndexDataService | None = None,
    ) -> None:
        if market_data_service is None or index_data_service is None:
            raise ValueError("PairCompareService 需要显式注入 market_data_service 和 index_data_service")
        self.market_data_service = market_data_service
        self.index_data_service = index_data_service

    def compare_pairs(self, symbol_a: str, symbol_b: str, days: int = 7, timeframe: str = "1h") -> dict:
        try:
            resolved_a = self._resolve_symbol(symbol_a)
            resolved_b = self._resolve_symbol(symbol_b)
            resolved_timeframe = "1d" if resolved_a["asset_class"] == "index" or resolved_b["asset_class"] == "index" else timeframe
            logger.info(f"开始对比: {resolved_a['symbol']} vs {resolved_b['symbol']}, {days}天, 显示周期{resolved_timeframe}")

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            base_timeframe = settings.PAIR_COMPARE_BASE_TIMEFRAME
            klines_a = self._fetch_history(resolved_a, start_date, end_date, base_timeframe)
            klines_b = self._fetch_history(resolved_b, start_date, end_date, base_timeframe)
            if not klines_a or not klines_b:
                return {"error": "获取数据失败"}

            if resolved_timeframe != base_timeframe:
                klines_a = self._aggregate_klines(klines_a, resolved_timeframe)
                klines_b = self._aggregate_klines(klines_b, resolved_timeframe)

            aligned = self._align_timestamps(klines_a, klines_b)
            if not aligned["timestamps"]:
                return {"error": "数据时间戳无法对齐"}

            return {
                "symbol_a": resolved_a["symbol"],
                "symbol_b": resolved_b["symbol"],
                "data_a": self._format_for_chart(aligned["data_a"]),
                "data_b": self._format_for_chart(aligned["data_b"]),
                "ratio_ohlc": self._calculate_ratio_ohlc(aligned["data_a"], aligned["data_b"]),
                "ratio_symbol": f"{resolved_a['symbol']}/{resolved_b['symbol']}",
                "timeframe": resolved_timeframe,
            }
        except Exception as exc:
            logger.error(f"币种对比失败: {exc}")
            return {"error": str(exc)}

    def _resolve_symbol(self, symbol: str) -> dict[str, str]:
        resolved = resolve_market_asset(symbol)
        if not resolved:
            raise ValueError(f"无效标的 {symbol}")
        if resolved["asset_class"] == "cash":
            raise ValueError(f"标的不支持对比 {symbol}")
        return resolved

    def _fetch_history(
        self,
        resolved: dict[str, str],
        start_date: datetime,
        end_date: datetime,
        base_timeframe: str,
    ) -> list[list[float]]:
        if resolved["asset_class"] == "index":
            result = self.index_data_service.get_history(
                symbol=resolved["symbol"],
                timeframe="1d",
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
            return [
                [point.timestamp, point.open, point.high, point.low, point.close, point.volume]
                for point in result.data
            ]
        return self.market_data_service.load_ohlcv_range(
            resolved["symbol"],
            base_timeframe,
            start_date,
            end_date,
        ).require_complete(symbol=resolved["symbol"], timeframe=base_timeframe)

    def _aggregate_klines(self, klines: list[list[float]], target_timeframe: str) -> list[list[float]]:
        interval_ms = timeframe_to_milliseconds(target_timeframe)
        if interval_ms <= 0:
            return klines
        aggregated: list[list[float]] = []
        current_bucket: list[float] | None = None
        for ts, open_price, high, low, close, volume in klines:
            bucket_start = (ts // interval_ms) * interval_ms
            if current_bucket is None or current_bucket[0] != bucket_start:
                if current_bucket:
                    aggregated.append(current_bucket)
                current_bucket = [bucket_start, open_price, high, low, close, volume]
                continue
            current_bucket[2] = max(current_bucket[2], high)
            current_bucket[3] = min(current_bucket[3], low)
            current_bucket[4] = close
            current_bucket[5] += volume
        if current_bucket:
            aggregated.append(current_bucket)
        return aggregated

    def _align_timestamps(self, klines_a: list[list[float]], klines_b: list[list[float]]) -> dict[str, list]:
        dict_a = {row[0]: row for row in klines_a}
        dict_b = {row[0]: row for row in klines_b}
        common_ts = sorted(set(dict_a.keys()) & set(dict_b.keys()))
        return {
            "timestamps": common_ts,
            "data_a": [dict_a[ts] for ts in common_ts],
            "data_b": [dict_b[ts] for ts in common_ts],
        }

    def _format_for_chart(self, klines: list[list[float]]) -> list[dict[str, float]]:
        return [
            {
                "time": int(row[0] / 1000),
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
            }
            for row in klines
        ]

    def _calculate_ratio_ohlc(self, klines_a: list[list[float]], klines_b: list[list[float]]) -> list[dict[str, float]]:
        ratio_klines = []
        for left, right in zip(klines_a, klines_b):
            if any(value in (0, None) for value in (left[1], left[2], left[3], left[4], right[1], right[2], right[3], right[4])):
                continue
            ratio_klines.append(
                {
                    "time": int(left[0] / 1000),
                    "open": left[1] / right[1],
                    "high": left[2] / right[2],
                    "low": left[3] / right[3],
                    "close": left[4] / right[4],
                }
            )
        return ratio_klines
