from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from app.domain.market.history.models import Instrument, PriceBar


EXCHANGE_CALENDARS = {
    "US": "XNYS",
    "CN": "XSHG",
    "HK": "XHKG",
    "COMEX": "CMES",
}


def resolve_date_range(
    instrument: Instrument,
    *,
    period: str | None,
    start: date | None,
    end: date | None,
    now: datetime | None = None,
) -> tuple[date, date]:
    if period and (start or end):
        raise ValueError("--period is mutually exclusive with --start/--end")
    if not period and not start:
        raise ValueError("provide --period or --start")
    effective_end = end or latest_completed_date(instrument, now=now)
    if period:
        if period == "max":
            effective_start = instrument.listed_on or date(1900, 1, 1)
        else:
            units = {
                "1mo": (1, 0), "3mo": (3, 0), "6mo": (6, 0),
                "1y": (0, 1), "3y": (0, 3), "5y": (0, 5), "10y": (0, 10),
            }
            if period not in units:
                raise ValueError("period must be 1mo, 3mo, 6mo, 1y, 3y, 5y, 10y or max")
            months, years = units[period]
            effective_start = _subtract_months(effective_end, months + years * 12)
    else:
        assert start is not None
        effective_start = start
        effective_end = end or latest_completed_date(instrument, now=now)
    if effective_start is None or effective_start > effective_end:
        raise ValueError("start must not be after end")
    return effective_start, effective_end


def latest_completed_date(instrument: Instrument, *, now: datetime | None = None) -> date:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if instrument.asset_class in {"crypto", "macro"}:
        return current.date() - timedelta(days=1)
    if instrument.asset_class == "fx":
        candidate = current.date() - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate
    calendar_name = _calendar_name(instrument)
    if calendar_name:
        try:
            import exchange_calendars as xcals

            calendar = xcals.get_calendar(calendar_name)
            local_now = current.astimezone(ZoneInfo(instrument.timezone))
            start = pd.Timestamp(local_now.date() - timedelta(days=10))
            finish = pd.Timestamp(local_now.date())
            sessions = calendar.sessions_in_range(start, finish)
            if len(sessions):
                today = pd.Timestamp(local_now.date())
                if today in sessions:
                    close = calendar.session_close(today).to_pydatetime()
                    if current >= close.astimezone(timezone.utc):
                        return local_now.date()
                return sessions[-2 if today in sessions and len(sessions) > 1 else -1].date()
        except Exception:
            pass
    candidate = current.date() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def coverage_report(
    instrument: Instrument,
    bars: tuple[PriceBar, ...],
    requested_start: date,
    requested_end: date,
    *,
    duplicate_dates: Sequence[date] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    actual_dates = [bar.observation_date for bar in bars]
    actual_set = set(actual_dates)
    expected, calendar_note = expected_dates(instrument, requested_start, requested_end)
    missing = sorted(set(expected) - actual_set)
    date_counts = Counter(actual_dates)
    reported_duplicates = sorted(
        set(duplicate_dates) | {item for item, count in date_counts.items() if count > 1}
    )
    issues: list[dict[str, Any]] = [
        {"type": "missing", "date": item, "detail": "provider returned no bar for an expected date"}
        for item in missing
    ]
    issues.extend(
        {"type": "duplicate", "date": item, "detail": "provider returned duplicate daily bars"}
        for item in reported_duplicates
    )
    reasons: list[str] = []
    if not bars:
        reasons.append("provider returned no usable records")
    if missing:
        reasons.append(f"{len(missing)} expected dates are missing")
    if reported_duplicates:
        reasons.append(f"{len(reported_duplicates)} dates are duplicated in the provider response")
    if (
        instrument.listed_on is None
        and instrument.asset_class in {"stock", "etf", "index", "commodity"}
        and bars and expected and bars[0].observation_date > expected[0]
    ):
        reasons.append("listing date is unknown and available data starts after the requested start")
    notes = [calendar_note] if calendar_note else []
    if calendar_note and instrument.asset_class != "fx":
        reasons.append(calendar_note)
    complete = not reasons
    report = {
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "actual_start": bars[0].observation_date.isoformat() if bars else None,
        "actual_end": bars[-1].observation_date.isoformat() if bars else None,
        "expected_trading_days": len(expected),
        "actual_records": len(bars),
        "missing_dates": [item.isoformat() for item in missing],
        "duplicate_dates": [item.isoformat() for item in reported_duplicates],
        "complete": complete,
        "incomplete_reasons": reasons,
        "method_notes": notes,
    }
    return report, issues


def expected_dates(
    instrument: Instrument,
    start: date,
    end: date,
) -> tuple[list[date], str | None]:
    effective_start = max(start, instrument.listed_on) if instrument.listed_on else start
    if instrument.asset_class in {"crypto", "macro"}:
        return _natural_days(effective_start, end), None
    if instrument.asset_class == "fx":
        return _weekdays(effective_start, end), "FX holidays vary by venue; weekday coverage is approximate"
    calendar_name = _calendar_name(instrument)
    if calendar_name:
        try:
            import exchange_calendars as xcals

            sessions = xcals.get_calendar(calendar_name).sessions_in_range(
                pd.Timestamp(effective_start), pd.Timestamp(end),
            )
            return [item.date() for item in sessions], None
        except Exception as exc:
            return _weekdays(effective_start, end), f"exchange calendar unavailable; weekday fallback used: {exc}"
    return _weekdays(effective_start, end), "exchange calendar is unknown; weekday coverage is approximate"


def _calendar_name(instrument: Instrument) -> str | None:
    if instrument.asset_class == "commodity" and instrument.exchange in {
        "COMEX", "NYMEX", "CBOT", "CME",
    }:
        return "CMES"
    if instrument.exchange in {"XNYS", "XNAS", "ARCX", "US"} or instrument.market == "US":
        return "XNYS"
    if instrument.exchange in {"XSHG", "XSHE", "SH", "SZ", "BJ"} or instrument.market == "CN":
        return "XSHG"
    if instrument.exchange in {"XHKG", "HK"} or instrument.market == "HK":
        return "XHKG"
    return EXCHANGE_CALENDARS.get(instrument.market)


def _natural_days(start: date, end: date) -> list[date]:
    return [item.date() for item in pd.date_range(start, end, freq="D")]


def _weekdays(start: date, end: date) -> list[date]:
    return [item.date() for item in pd.date_range(start, end, freq="B")]


def _subtract_months(value: date, months: int) -> date:
    year = value.year - (months // 12)
    month = value.month - (months % 12)
    if month <= 0:
        month += 12
        year -= 1
    month_end = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(value.day, month_end))
