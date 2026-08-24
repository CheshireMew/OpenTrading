from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.persistence_ports import FundingRateStorePort
from utils.logger import logger
from .binance_numbers import safe_float


class FundingRateService:
    EXCHANGE = "binance"
    MARKET_TYPE = "usdm"
    BASE_URL = "https://fapi.binance.com"
    HISTORY_LIMIT = 1000
    DEFAULT_START_DATE = "2019-09-01"

    def __init__(self, store: FundingRateStorePort) -> None:
        self.store = store

    def fetch_current_rate(self, symbol: str) -> dict[str, Any]:
        normalized_symbol = self.normalize_symbol(symbol)
        response = httpx.get(
            f"{self.BASE_URL}/fapi/v1/premiumIndex",
            params={"symbol": normalized_symbol},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "exchange": self.EXCHANGE,
            "market_type": self.MARKET_TYPE,
            "symbol": normalized_symbol,
            "funding_rate": safe_float(payload.get("lastFundingRate")),
            "funding_rate_pct": self._ratio_to_pct(payload.get("lastFundingRate")),
            "mark_price": safe_float(payload.get("markPrice")),
            "index_price": safe_float(payload.get("indexPrice")),
            "interest_rate": safe_float(payload.get("interestRate")),
            "next_funding_time": self._to_iso(payload.get("nextFundingTime")),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    def sync_history(
        self,
        symbol: str,
        *,
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
    ) -> dict[str, Any]:
        normalized_symbol = self.normalize_symbol(symbol)
        resolved_start = self._parse_date(start_date or self.DEFAULT_START_DATE)
        resolved_end = self._parse_date(end_date) if end_date else datetime.now(timezone.utc)
        if resolved_end <= resolved_start:
            raise ValueError("结束时间必须晚于开始时间")

        fetched_rows = 0
        inserted_rows = 0
        cursor_ms = self._to_millis(resolved_start)
        end_ms = self._to_millis(resolved_end)

        with httpx.Client(timeout=20.0) as client:
            while cursor_ms < end_ms:
                response = client.get(
                    f"{self.BASE_URL}/fapi/v1/fundingRate",
                    params={
                        "symbol": normalized_symbol,
                        "startTime": cursor_ms,
                        "endTime": end_ms,
                        "limit": self.HISTORY_LIMIT,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not payload:
                    break

                rows = [self._history_row(item) for item in payload]
                fetched_rows += len(rows)
                inserted_rows += self.store.save_many(rows)

                last_funding_ms = int(payload[-1]["fundingTime"])
                if last_funding_ms < cursor_ms:
                    break
                cursor_ms = last_funding_ms + 1

                if len(payload) < self.HISTORY_LIMIT:
                    break
                time.sleep(0.2)

        total_rows = self.store.count(
            exchange=self.EXCHANGE,
            market_type=self.MARKET_TYPE,
            symbol=normalized_symbol,
        )
        logger.info(
            f"资金费率同步完成: symbol={normalized_symbol}, fetched={fetched_rows}, inserted={inserted_rows}, total={total_rows}"
        )
        return {
            "exchange": self.EXCHANGE,
            "market_type": self.MARKET_TYPE,
            "symbol": normalized_symbol,
            "fetched": fetched_rows,
            "inserted": inserted_rows,
            "total": total_rows,
            "start_date": resolved_start.isoformat(),
            "end_date": resolved_end.isoformat(),
        }

    def get_history(
        self,
        symbol: str,
        *,
        start_date: str | datetime | None = None,
        end_date: str | datetime | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        normalized_symbol = self.normalize_symbol(symbol)
        resolved_start = self._parse_date(start_date) if start_date else None
        resolved_end = self._parse_date(end_date) if end_date else None
        rows = self.store.list_history(
            exchange=self.EXCHANGE,
            market_type=self.MARKET_TYPE,
            symbol=normalized_symbol,
            start_date=resolved_start,
            end_date=resolved_end,
            limit=limit,
        )
        return {
            "exchange": self.EXCHANGE,
            "market_type": self.MARKET_TYPE,
            "symbol": normalized_symbol,
            "count": len(rows),
            "items": [
                {
                    "funding_time": item["funding_time"].replace(tzinfo=timezone.utc).isoformat(),
                    "funding_rate": item["funding_rate"],
                    "funding_rate_pct": item["funding_rate"] * 100.0,
                    "mark_price": item["mark_price"],
                }
                for item in rows
            ],
        }

    def normalize_symbol(self, symbol: str) -> str:
        value = symbol.strip().upper()
        if not value:
            raise ValueError("symbol 不能为空")

        if ":" in value:
            value = value.split(":", 1)[0]
        if "/" in value:
            base, quote = value.split("/", 1)
            if quote != "USDT":
                raise ValueError("当前只支持 Binance U 本位永续合约，例如 BTCUSDT")
            value = f"{base}{quote}"

        if not value.endswith("USDT"):
            raise ValueError("当前只支持 Binance U 本位永续合约，例如 BTCUSDT")
        return value

    def _history_row(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "exchange": self.EXCHANGE,
            "market_type": self.MARKET_TYPE,
            "symbol": self.normalize_symbol(payload["symbol"]),
            "funding_time": self._from_millis(int(payload["fundingTime"])),
            "funding_rate": float(payload["fundingRate"]),
            "mark_price": safe_float(payload.get("markPrice")),
        }

    def _parse_date(self, value: str | datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            if value.tzinfo:
                return value.astimezone(timezone.utc)
            return value.replace(tzinfo=timezone.utc)

        text = value.strip()
        if "T" in text:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc)
        return parsed.replace(tzinfo=timezone.utc)

    def _to_millis(self, value: datetime) -> int:
        return int(value.timestamp() * 1000)

    def _from_millis(self, value: int) -> datetime:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None, microsecond=0)

    def _to_iso(self, value: Any) -> str | None:
        if value in (None, "", 0):
            return None
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()

    def _ratio_to_pct(self, value: Any) -> float | None:
        ratio = safe_float(value)
        if ratio is None:
            return None
        return ratio * 100.0
