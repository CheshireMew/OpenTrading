from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroIndicatorSource:
    fred_id: str | None
    yf_ticker: str | None
    indicator_id: str


MACRO_INDICATOR_SOURCES: tuple[MacroIndicatorSource, ...] = (
    MacroIndicatorSource("DGS10", "^TNX", "US10Y"),
    MacroIndicatorSource("DGS2", None, "US02Y"),
    MacroIndicatorSource("NASDAQCOM", "^IXIC", "NASDAQ"),
    MacroIndicatorSource("FEDFUNDS", None, "FED_RATE"),
    MacroIndicatorSource("DCOILWTICO", "CL=F", "WTI"),
)


MARKET_INDICATOR_META: dict[str, tuple[str, str, str]] = {
    "US10Y": ("US 10Y Treasury Yield", "Macro", "%"),
    "NASDAQ": ("NASDAQ Composite", "Macro", ""),
    "GOLD": ("Gold Spot Price", "Macro", "USD"),
    "FED_RATE": ("Fed Funds Rate", "Macro", "%"),
    "US02Y": ("US 2Y Treasury Yield", "Macro", "%"),
    "WTI": ("WTI Crude Oil", "Macro", "USD"),
    "HASHRATE": ("BTC Hashrate", "Onchain", "EH/s"),
    "DIFFICULTY": ("Mining Difficulty", "Onchain", "T"),
    "STABLECOIN_CAP": ("Stablecoin Market Cap", "Onchain", "USD"),
    "USDT_CAP": ("USDT Market Cap", "Onchain", "USD"),
    "USDC_CAP": ("USDC Market Cap", "Onchain", "USD"),
    "FEAR_GREED": ("Fear & Greed Index", "Sentiment", ""),
    "GOOGLE_TRENDS_BTC": ("Google Trends: BTC", "Sentiment", ""),
    "200WMA": ("200-Week Moving Avg", "Tech", "USD"),
    "S19_BREAKEVEN": ("S19 Miner Breakeven", "Tech", "USD"),
    "S21_BREAKEVEN": ("S21 Miner Breakeven", "Tech", "USD"),
    "S23_BREAKEVEN": ("S23 Miner Breakeven", "Tech", "USD"),
    "BTC_DRAWDOWN": ("BTC Drawdown from ATH", "Tech", "%"),
}


def market_indicator_meta_catalog() -> dict[str, tuple[str, str, str]]:
    return dict(MARKET_INDICATOR_META)
