from __future__ import annotations

MARKET_INDICATOR_META: dict[str, tuple[str, str, str]] = {
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
