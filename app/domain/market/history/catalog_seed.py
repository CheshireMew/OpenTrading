from __future__ import annotations

from datetime import date
from collections.abc import Iterable

from app.domain.market.history.catalog_conventions import (
    FX_FRED_SERIES,
    INDEX_PROVIDER_SYMBOLS,
)
from app.domain.market.history.catalog_record import CatalogRecord
from app.domain.market.history.models import Instrument


CATALOG_SEED_VERSION = 3


def seed_records() -> Iterable[CatalogRecord]:
    rows = (
        (
            Instrument("600519.SH", "贵州茅台", "stock", "CN", "XSHG", "CNY", "Asia/Shanghai", date(2001, 8, 27)),
            {("贵州茅台", "chinese_name"), ("茅台", "short_name"), ("600519", "common_code")},
            {"akshare": "600519", "baostock": "sh.600519", "yfinance": "600519.SS"},
        ),
        (
            Instrument("AAPL.US", "Apple Inc.", "stock", "US", "XNAS", "USD", "America/New_York", date(1980, 12, 12)),
            {("Apple", "english_name"), ("苹果", "chinese_name"), ("AAPL", "common_code")},
            {"yfinance": "AAPL", "akshare": "105.AAPL", "tiingo": "AAPL"},
        ),
        (
            Instrument("00700.HK", "腾讯控股", "stock", "HK", "XHKG", "HKD", "Asia/Hong_Kong", date(2004, 6, 16)),
            {("腾讯", "short_name"), ("Tencent", "english_name"), ("0700.HK", "common_code"), ("700", "common_code")},
            {"yfinance": "0700.HK", "akshare": "00700"},
        ),
        (
            Instrument("SPY.US", "SPDR S&P 500 ETF Trust", "etf", "US", "ARCX", "USD", "America/New_York", date(1993, 1, 22)),
            {("SPY", "common_code"), ("标普500ETF", "chinese_name")},
            {"yfinance": "SPY", "akshare": "105.SPY", "tiingo": "SPY"},
        ),
        (
            Instrument("QQQ.US", "Invesco QQQ Trust", "etf", "US", "XNAS", "USD", "America/New_York", date(1999, 3, 10)),
            {("QQQ", "common_code"), ("纳指ETF", "chinese_name")},
            {"yfinance": "QQQ", "akshare": "105.QQQ", "tiingo": "QQQ"},
        ),
        (
            Instrument("GLD.US", "SPDR Gold Shares", "etf", "US", "ARCX", "USD", "America/New_York", date(2004, 11, 18)),
            {("GLD", "common_code"), ("黄金", "generic_name"), ("黄金ETF", "chinese_name")},
            {"yfinance": "GLD", "tiingo": "GLD"},
        ),
        (
            Instrument("SPX.INDEX", "S&P 500 Index", "index", "US", "XNYS", "USD", "America/New_York"),
            {("SPX", "common_code"), ("标普500", "chinese_name"), ("S&P 500", "english_name")},
            {"yfinance": "^GSPC"},
        ),
        (
            Instrument("CSI300.INDEX", "沪深300指数", "index", "CN", "XSHG", "CNY", "Asia/Shanghai", date(2005, 4, 8)),
            {("沪深300", "chinese_name"), ("CSI 300", "english_name"), ("000300", "common_code")},
            {"akshare": "sh000300", "baostock": "sh.000300", "yfinance": "000300.SS"},
        ),
        (
            Instrument("HSI.INDEX", "恒生指数", "index", "HK", "XHKG", "HKD", "Asia/Hong_Kong", date(1969, 11, 24)),
            {("恒指", "short_name"), ("Hang Seng Index", "english_name")},
            {"yfinance": "^HSI"},
        ),
        (
            Instrument(
                "BTC/USDT@BINANCE", "Bitcoin / Tether", "crypto", "crypto", "BINANCE",
                "USDT", "UTC", date(2017, 8, 17),
            ),
            {("BTCUSDT", "common_code"), ("比特币", "chinese_name"), ("Bitcoin", "english_name")},
            {"binance": "BTCUSDT"},
        ),
        (
            Instrument(
                "ETH/USDT@BINANCE", "Ether / Tether", "crypto", "crypto", "BINANCE",
                "USDT", "UTC", date(2017, 8, 17),
            ),
            {("ETHUSDT", "common_code"), ("以太坊", "chinese_name"), ("Ethereum", "english_name")},
            {"binance": "ETHUSDT"},
        ),
        (
            Instrument("EUR/USD", "Euro / US Dollar", "fx", "global", "OTC", "USD", "UTC"),
            {("EURUSD", "common_code"), ("欧元美元", "chinese_name")},
            {"yfinance": "EURUSD=X", "fred": "DEXUSEU"},
        ),
        (
            Instrument("GC1.COMEX", "COMEX Gold Continuous Contract", "commodity", "US", "COMEX", "USD", "America/New_York", is_continuous=True),
            {("黄金", "generic_name"), ("黄金期货", "chinese_name"), ("COMEX黄金", "chinese_name")},
            {"yfinance": "GC=F", "akshare": "GC"},
        ),
        (
            Instrument("FRED:DGS10", "10-Year Treasury Constant Maturity Rate", "macro", "US", "FRED", "percent", "UTC"),
            {("DGS10", "common_code"), ("美国十年期国债收益率", "chinese_name")},
            {"fred": "DGS10"},
        ),
        (
            Instrument("DXY.INDEX", "US Dollar Index (DXY)", "index", "US", "ICEUS", "USD", "America/New_York"),
            {("DXY", "common_code"), ("USDX", "common_code"), ("美元指数", "chinese_name"), ("美指", "short_name"), ("DX-Y.NYB", "provider_symbol")},
            {"yfinance": "DX-Y.NYB"},
        ),
        (
            Instrument("BNB/USDT@BINANCE", "BNB / Tether", "crypto", "crypto", "BINANCE", "USDT", "UTC"),
            {("BNBUSDT", "common_code"), ("币安币", "chinese_name"), ("BNB", "short_name")},
            {"binance": "BNBUSDT"},
        ),
        (
            Instrument("SOL/USDT@BINANCE", "Solana / Tether", "crypto", "crypto", "BINANCE", "USDT", "UTC"),
            {("SOLUSDT", "common_code"), ("Solana", "english_name"), ("SOL", "short_name")},
            {"binance": "SOLUSDT"},
        ),
        (
            Instrument("XRP/USDT@BINANCE", "XRP / Tether", "crypto", "crypto", "BINANCE", "USDT", "UTC"),
            {("XRPUSDT", "common_code"), ("XRP", "short_name")},
            {"binance": "XRPUSDT"},
        ),
        (
            Instrument("ADA/USDT@BINANCE", "Cardano / Tether", "crypto", "crypto", "BINANCE", "USDT", "UTC"),
            {("ADAUSDT", "common_code"), ("Cardano", "english_name"), ("ADA", "short_name")},
            {"binance": "ADAUSDT"},
        ),
        (
            Instrument("DOGE/USDT@BINANCE", "Dogecoin / Tether", "crypto", "crypto", "BINANCE", "USDT", "UTC"),
            {("DOGEUSDT", "common_code"), ("Dogecoin", "english_name"), ("DOGE", "short_name")},
            {"binance": "DOGEUSDT"},
        ),
        *(
            (
                Instrument(code, name, "fx", "global", "OTC", code.split("/")[1], "UTC"),
                {(code.replace("/", ""), "common_code"), (alias, "chinese_name")},
                {"yfinance": f"{code.replace('/', '')}=X", "fred": FX_FRED_SERIES[code]},
            )
            for code, name, alias in (
                ("USD/JPY", "US Dollar / Japanese Yen", "美元日元"),
                ("GBP/USD", "British Pound / US Dollar", "英镑美元"),
                ("AUD/USD", "Australian Dollar / US Dollar", "澳元美元"),
                ("USD/CAD", "US Dollar / Canadian Dollar", "美元加元"),
                ("USD/CHF", "US Dollar / Swiss Franc", "美元瑞郎"),
                ("NZD/USD", "New Zealand Dollar / US Dollar", "纽元美元"),
            )
        ),
        *(
            (
                Instrument(
                    code, name, "commodity", "US", exchange, "USD", "America/New_York",
                    is_continuous=True,
                ),
                {(root, "common_code"), (alias, "chinese_name")},
                {"yfinance": f"{root}=F", "akshare": root},
            )
            for code, root, exchange, name, alias in (
                ("SI1.COMEX", "SI", "COMEX", "COMEX Silver Continuous Contract", "白银期货"),
                ("HG1.COMEX", "HG", "COMEX", "COMEX Copper Continuous Contract", "铜期货"),
                ("CL1.NYMEX", "CL", "NYMEX", "WTI Crude Oil Continuous Contract", "WTI原油期货"),
                ("NG1.NYMEX", "NG", "NYMEX", "Natural Gas Continuous Contract", "天然气期货"),
                ("ZC1.CBOT", "ZC", "CBOT", "Corn Continuous Contract", "玉米期货"),
                ("ZW1.CBOT", "ZW", "CBOT", "Wheat Continuous Contract", "小麦期货"),
                ("ZS1.CBOT", "ZS", "CBOT", "Soybean Continuous Contract", "大豆期货"),
            )
        ),
        *(
            (
                Instrument(code, name, "index", market, exchange, currency, timezone),
                {(alias, "common_code"), (chinese, "chinese_name")},
                {"yfinance": INDEX_PROVIDER_SYMBOLS[code]},
            )
            for code, name, market, exchange, currency, timezone, alias, chinese in (
                ("DJI.INDEX", "Dow Jones Industrial Average", "US", "XNYS", "USD", "America/New_York", "DJI", "道琼斯指数"),
                ("IXIC.INDEX", "Nasdaq Composite", "US", "XNAS", "USD", "America/New_York", "IXIC", "纳斯达克综合指数"),
                ("NDX.INDEX", "Nasdaq-100 Index", "US", "XNAS", "USD", "America/New_York", "NDX", "纳斯达克100指数"),
                ("RUT.INDEX", "Russell 2000 Index", "US", "XNYS", "USD", "America/New_York", "RUT", "罗素2000指数"),
                ("VIX.INDEX", "CBOE Volatility Index", "US", "XNYS", "USD", "America/New_York", "VIX", "恐慌指数"),
            )
        ),
    )
    for instrument, aliases, mappings in rows:
        yield CatalogRecord(instrument, aliases, mappings, priority=10)
