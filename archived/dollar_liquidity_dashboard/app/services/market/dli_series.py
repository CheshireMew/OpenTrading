from __future__ import annotations

import math
from datetime import datetime
from typing import Any


class DliSeriesBuilder:
    def with_derived_indicators(self, history_map: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        result = {key: list(value) for key, value in history_map.items()}
        if "SOFR_IORB" not in result:
            result["SOFR_IORB"] = self._derive_pair_spread(
                result.get("SOFR", []),
                result.get("IORB", []),
                scale=100.0,
            )
        if "SRF_USAGE" not in result:
            result["SRF_USAGE"] = list(result.get("RPONTSYD", []))
        if "BANK_CASH_BUFFER" not in result:
            result["BANK_CASH_BUFFER"] = self._derive_ratio_percent(
                result.get("CASACBW027SBOG", []),
                result.get("TLAACBW027SBOG", []),
            )
        if "US10Y_REAL" not in result:
            result["US10Y_REAL"] = list(result.get("DFII10", []))
        if "NET_LIQUIDITY" not in result:
            result["NET_LIQUIDITY"] = self._derive_net_liquidity(
                result.get("FED_BALANCE", []),
                result.get("TGA", []),
                result.get("ONRRP", []),
            )
        return result

    def points_map(self, history_map: dict[str, list[dict[str, Any]]]) -> dict[str, list[tuple[datetime, float]]]:
        result: dict[str, list[tuple[datetime, float]]] = {}
        for indicator_id, rows in history_map.items():
            points = [
                (item["timestamp"], float(item["value"]))
                for item in rows
                if item.get("timestamp") is not None
                and item.get("value") is not None
                and math.isfinite(float(item["value"]))
            ]
            result[indicator_id] = sorted(points, key=lambda item: item[0])
        return result

    def latest_update(self, history_map: dict[str, list[dict[str, Any]]]) -> datetime | None:
        dates = [
            item["timestamp"]
            for rows in history_map.values()
            for item in rows
            if item.get("timestamp") is not None
        ]
        return max(dates) if dates else None

    def _derive_pair_spread(
        self,
        left_rows: list[dict[str, Any]],
        right_rows: list[dict[str, Any]],
        *,
        scale: float = 1.0,
    ) -> list[dict[str, Any]]:
        left_raw = self._values_by_date(left_rows)
        right_raw = self._values_by_date(right_rows)
        dates = sorted(set(left_raw) | set(right_raw))
        left = self._carry_forward_values(left_raw, dates)
        right = self._carry_forward_values(right_raw, dates)
        derived = []
        for timestamp in dates:
            if timestamp not in left or timestamp not in right:
                continue
            value = (left[timestamp] - right[timestamp]) * scale
            derived.append({"date": timestamp.isoformat(), "timestamp": timestamp, "value": value})
        return derived

    def _derive_net_liquidity(
        self,
        fed_rows: list[dict[str, Any]],
        tga_rows: list[dict[str, Any]],
        onrrp_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        fed_raw = self._values_by_date(fed_rows)
        tga_raw = self._values_by_date(tga_rows)
        onrrp_raw = self._values_by_date(onrrp_rows)
        dates = sorted(set(fed_raw) | set(tga_raw) | set(onrrp_raw))
        fed = self._carry_forward_values(fed_raw, dates)
        tga = self._carry_forward_values(tga_raw, dates)
        onrrp = self._carry_forward_values(onrrp_raw, dates)
        derived = []
        for timestamp in dates:
            if timestamp not in fed or timestamp not in tga or timestamp not in onrrp:
                continue
            value = fed[timestamp] - tga[timestamp] - onrrp[timestamp] * 1000.0
            derived.append({"date": timestamp.isoformat(), "timestamp": timestamp, "value": value})
        return derived

    def _derive_ratio_percent(
        self,
        numerator_rows: list[dict[str, Any]],
        denominator_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        numerator_raw = self._values_by_date(numerator_rows)
        denominator_raw = self._values_by_date(denominator_rows)
        dates = sorted(set(numerator_raw) | set(denominator_raw))
        numerator = self._carry_forward_values(numerator_raw, dates)
        denominator = self._carry_forward_values(denominator_raw, dates)
        derived = []
        for timestamp in dates:
            if timestamp not in numerator or timestamp not in denominator or denominator[timestamp] == 0:
                continue
            value = numerator[timestamp] / denominator[timestamp] * 100.0
            derived.append({"date": timestamp.isoformat(), "timestamp": timestamp, "value": value})
        return derived

    @staticmethod
    def _values_by_date(rows: list[dict[str, Any]]) -> dict[datetime, float]:
        values = {}
        for row in rows:
            timestamp = row.get("timestamp")
            value = row.get("value")
            if isinstance(timestamp, datetime) and value is not None:
                values[timestamp] = float(value)
        return values

    @staticmethod
    def _carry_forward_values(values: dict[datetime, float], dates: list[datetime]) -> dict[datetime, float]:
        carried = {}
        latest = None
        for date in dates:
            if date in values:
                latest = values[date]
            if latest is not None:
                carried[date] = latest
        return carried
