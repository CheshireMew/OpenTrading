"""Verified exchange-session calendars; unsupported dates fail explicitly."""
from datetime import date, timedelta
from functools import lru_cache

import exchange_calendars


@lru_cache(maxsize=24)
def session_dates(market: str, start: date, end: date) -> tuple[str, list[str], list[str]]:
    code = {"US": "XNYS", "CN": "XSHG", "HK": "XHKG", "ICEUS": "ICEUS"}[market]
    if end < start:
        return code, [], []
    calendar = exchange_calendars.get_calendar(code, start=(start - timedelta(days=14)).isoformat(), end=end.isoformat())
    sessions = [stamp.date().isoformat() for stamp in calendar.sessions if start <= stamp.date() <= end]
    present = set(sessions)
    non_trading = [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)
                   if (start + timedelta(days=offset)).isoformat() not in present]
    return code, sessions, non_trading
