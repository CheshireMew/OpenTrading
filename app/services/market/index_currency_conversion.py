from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone


FxRateFetcher = Callable[[str, datetime, datetime], dict[str, float]]


def convert_ohlcv_rows_to_usd(
    rows: list[list[float]],
    native_currency: str,
    start_at: datetime,
    end_at: datetime,
    fetch_rates: FxRateFetcher,
) -> list[list[float]]:
    currency = str(native_currency or "").upper()
    if currency in {"", "USD", "USDT"}:
        return rows

    fx_rates = fetch_rates(currency, start_at, end_at)
    converted: list[list[float]] = []
    last_rate: float | None = None
    for row in rows:
        row_date = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        rate = fx_rates.get(row_date) or last_rate
        if not rate:
            continue
        last_rate = rate
        converted.append([
            row[0],
            row[1] * rate,
            row[2] * rate,
            row[3] * rate,
            row[4] * rate,
            row[5],
        ])
    return converted
