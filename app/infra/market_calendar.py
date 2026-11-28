"""Verified exchange-session calendars; unsupported dates fail explicitly."""
from datetime import date, timedelta
from functools import lru_cache

import exchange_calendars
from pandas import DatetimeIndex


# Official HKEX full-day cancellations, absent from exchange-calendars 4.13.2.
# https://www.hkex.com.hk/News/Market-Communications/2023/2309012news
# https://www.hkex.com.hk/News/Market-Communications/2023/2309083news
_HKEX_CLOSURES = {date(2023, 9, 1), date(2023, 9, 8)}


@lru_cache(maxsize=24)
def session_dates(market: str, start: date, end: date) -> tuple[str, list[str], list[str]]:
    code = {"US": "XNYS", "CN": "XSHG", "HK": "XHKG", "ICEUS": "ICEUS"}[market]
    if end < start:
        return code, [], []
    calendar = exchange_calendars.get_calendar(code, start=(start - timedelta(days=14)).isoformat(), end=end.isoformat())
    # The dependency's generated sessions can retain pre-1970 holidays on
    # Windows even though its holiday rules correctly identify those dates.
    regular = calendar.regular_holidays
    holidays = {stamp.date() for stamp in regular.holidays(start,end)} if regular is not None else set()
    holidays.update(DatetimeIndex(calendar.adhoc_holidays).date)
    if code == "XHKG":
        holidays.update(_HKEX_CLOSURES)
    sessions = [stamp.date().isoformat() for stamp in calendar.sessions
        if start <= stamp.date() <= end and stamp.date() not in holidays]
    present = set(sessions)
    non_trading = [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)
                   if (start + timedelta(days=offset)).isoformat() not in present]
    return code, sessions, non_trading
