from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from signal_lab.data.http import HttpTransport, UrllibJsonTransport


SPOT_API = "https://api.binance.com"
FUTURES_API = "https://fapi.binance.com"


class BinanceKlineClient:
    """Own Binance market discovery and paginated kline acquisition."""

    def __init__(self, transport: HttpTransport | None = None) -> None:
        self.transport = transport or UrllibJsonTransport()

    def market_exists(self, symbol: str, *, spot: bool) -> bool:
        base = SPOT_API if spot else FUTURES_API
        path = "/api/v3/exchangeInfo" if spot else "/fapi/v1/exchangeInfo"
        payload = self.transport.get_json(f"{base}{path}", {}, {})
        if not isinstance(payload, dict):
            return False
        symbols = payload.get("symbols", [])
        return any(
            isinstance(item, dict)
            and item.get("symbol") == symbol
            and item.get("status") == "TRADING"
            for item in symbols
        )

    def download_klines(
        self,
        *,
        spot: bool,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        now_ms: int | None = None,
    ) -> list[list[Any]]:
        base = SPOT_API if spot else FUTURES_API
        path = "/api/v3/klines" if spot else "/fapi/v1/klines"
        cursor = start_ms
        current_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
        rows: list[list[Any]] = []
        while cursor < end_ms:
            page = self.transport.get_json(
                f"{base}{path}",
                {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": str(cursor),
                    "endTime": str(end_ms - 1),
                    "limit": "1000",
                },
                {},
            )
            if not isinstance(page, list) or not page:
                break
            rows.extend(
                row
                for row in page
                if isinstance(row, list)
                and len(row) > 6
                and int(row[6]) <= min(end_ms, current_ms)
            )
            next_cursor = int(page[-1][0]) + 1
            if next_cursor <= cursor or len(page) < 1000:
                break
            cursor = next_cursor
        deduplicated = {int(row[0]): row for row in rows}
        return [deduplicated[key] for key in sorted(deduplicated)]
