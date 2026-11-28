"""Chart identities describe index levels, independently of ETF pricing proxies."""
from app.contracts.chart_workspace import ChartSymbol
from app.domain.market.index_catalog import INDEX_CATALOG
from app.infra.market_data.index_source_catalog import get_index_source_binding
from app.domain.market.index_history_policy import live_start_ms

PERIODS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]
RETENTION = {"1m": 29, "5m": 59, "15m": 59, "30m": 59, "1h": 729, "4h": 729}
# These are ticker badges, not the index administrator's corporate logo.
IDENTITIES = {
    "US_SP500": ("SPX", "标普500指数", "S&P 500 Index", "S&P DJI"),
    "US_NASDAQ_COMP": ("IXIC", "纳斯达克综合指数", "Nasdaq Composite Index", "NASDAQ"),
    "US_NASDAQ100": ("NDX", "纳斯达克100指数", "Nasdaq 100 Index", "NASDAQ"),
    "US_DOW": ("DJI", "道琼斯工业平均指数", "Dow Jones Industrial Average", "S&P DJI"),
    "US_RUSSELL2000": ("RUT", "罗素2000指数", "Russell 2000 Index", "FTSE RUSSELL"),
    "US_VIX": ("VIX", "恐慌指数", "Cboe Volatility Index", "CBOE"),
    "US_DXY": ("DXY", "美元指数", "US Dollar Index", "ICE"),
    "CN_CSI300": ("CSI300", "沪深300指数", "CSI 300 Index", "CSI"),
    "CN_CSI_A500": ("A500", "中证A500指数", "CSI A500 Index", "CSI"),
    "CN_SSE50": ("SSE50", "上证50指数", "SSE 50 Index", "SSE"),
    "CN_CSI500": ("CSI500", "中证500指数", "CSI 500 Index", "CSI"),
    "CN_CSI1000": ("CSI1000", "中证1000指数", "CSI 1000 Index", "CSI"),
    "CN_SSE_COMP": ("SSE", "上证指数", "SSE Composite Index", "SSE"),
    "CN_SZSE_COMPONENT": ("SZSE", "深证成指", "SZSE Component Index", "SZSE"),
    "CN_CHINEXT": ("CHINEXT", "创业板指", "ChiNext Index", "SZSE"),
    "CN_STAR50": ("STAR50", "科创50指数", "STAR 50 Index", "SSE"),
    "HK_HSI": ("HSI", "恒生指数", "Hang Seng Index", "HSI"),
    "HK_HSTECH": ("HSTECH", "恒生科技指数", "Hang Seng TECH Index", "HSI"),
    "HK_HSCEI": ("HSCEI", "恒生中国企业指数", "Hang Seng China Enterprises Index", "HSI"),
}


def index_symbol(symbol: str) -> ChartSymbol:
    instrument = INDEX_CATALOG[symbol]
    ticker, name_zh, name_en, exchange = IDENTITIES[symbol]
    timezone, session = {
        "US": ("America/New_York", "0930-1600:23456"),
        "CN": ("Asia/Shanghai", "0930-1130,1300-1500:23456"),
        "HK": ("Asia/Hong_Kong", "0930-1200,1300-1600:23456"),
    }[instrument.market]
    if symbol == "US_VIX":
        timezone, session = "America/Chicago", "0200-1515:23456"
    elif symbol == "US_DXY":
        session = "1800-1700:23456"
    offset = 0 if symbol in {"US_DXY", "US_VIX"} else 1_800_000
    source_ticker = get_index_source_binding(symbol).yfinance_symbol
    return ChartSymbol(id=f"index:index:{symbol}", symbol=symbol, name=name_en, exchange=exchange,
        market="index", currency="PTS", timezone=timezone, session=session, timeframes=PERIODS,
        aliases=list(dict.fromkeys([instrument.name, *instrument.aliases, ticker, source_ticker, name_zh, name_en])),
        metadata={"display_symbol": ticker, "name_zh": name_zh, "name_en": name_en,
            "launch_date": instrument.launch_date, "history_start": live_start_ms(instrument), "history_policy": "live-only",
            "quote_unit": "points", "icon_url": f"/brand-icons/{ticker.lower()}.svg", "price_basis": "index",
            "mintick": 0.01, "minmove": 1, "pricescale": 100, "pointvalue": 1, "has_volume": False,
            "intraday_source": f"Yahoo Finance · {source_ticker}", "data_status": "delayed",
            "intraday_retention_days": RETENTION, "candle_offset_ms": {"1h": offset, "4h": offset}})
