from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class SessionHistoryCoverage:
    complete: bool = False
    calendar: str | None = None
    start_date: str = ""
    end_date: str = ""
    expected_sessions: list[str] = field(default_factory=list)
    missing_sessions: list[str] = field(default_factory=list)
    non_trading_dates: list[str] = field(default_factory=list)
    error: str | None = "Trading calendar coverage is unavailable"

    def require_complete(self):
        if not self.complete:
            raise ValueError(self.error or "缺少交易日行情：" + ", ".join(self.missing_sessions[:10]))


def daily_session_prices(prices: dict[str, float], coverage: SessionHistoryCoverage, start: date, end: date) -> dict[str, float]:
    coverage.require_complete()
    if coverage.start_date > start.isoformat() or coverage.end_date < end.isoformat():
        raise ValueError("交易日历没有覆盖所选区间")
    non_trading = set(coverage.non_trading_dates)
    prior = [day for day, price in prices.items() if day < start.isoformat() and price > 0]
    previous = prices[max(prior)] if prior else None
    result = {}
    for offset in range((end - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        value = prices.get(day)
        if value is not None and value > 0:
            previous = value
        elif day not in non_trading or previous is None:
            raise ValueError(f"{day} 缺少有效的交易日价格，不能作为休市日填充")
        result[day] = previous
    return result
