from __future__ import annotations

from datetime import date
from typing import Any


HISTORY_SCHEMA_VERSION = "signal-lab.history.v1"


def history_envelope(
    status: str,
    request: dict[str, Any],
    *,
    instrument: Any = None,
    coverage: Any = None,
    source: Any = None,
    price_basis: Any = None,
    statistics: Any = None,
    indicators: Any = None,
    artifact: Any = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build the shared prices/macro history response contract."""

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "status": status,
        "request": request,
        "instrument": instrument,
        "coverage": coverage,
        "source": source,
        "price_basis": price_basis,
        "statistics": statistics,
        "indicators": indicators,
        "artifact": artifact,
        "warnings": warnings or [],
    }


def empty_coverage(start: date, end: date) -> dict[str, Any]:
    return {
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "actual_start": None,
        "actual_end": None,
        "expected_trading_days": None,
        "actual_records": 0,
        "missing_dates": [],
        "complete": False,
        "incomplete_reasons": ["no usable snapshot"],
        "method_notes": [],
    }
