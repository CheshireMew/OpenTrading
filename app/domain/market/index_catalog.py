from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexInstrument:
    symbol: str
    name: str
    market: str
    currency: str
    storage_symbol: str
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None
    pricing_storage_symbol: str | None = None
    aliases: tuple[str, ...] = ()


INDEX_CATALOG: dict[str, IndexInstrument] = {
    "US_SP500": IndexInstrument(
        symbol="US_SP500",
        name="S&P 500",
        market="US",
        currency="USD",
        storage_symbol="index:US:SP500",
        pricing_symbol="SPY",
        pricing_name="SPDR S&P 500 ETF Trust",
        pricing_currency="USD",
        pricing_storage_symbol="proxy:US:SP500:SPY",
        aliases=("标普", "标普500", "SP500", "S&P", "S&P500", "SPX"),
    ),
    "US_NASDAQ_COMP": IndexInstrument(
        symbol="US_NASDAQ_COMP",
        name="Nasdaq Composite",
        market="US",
        currency="USD",
        storage_symbol="index:US:NASDAQ_COMP",
        pricing_symbol="ONEQ",
        pricing_name="Fidelity Nasdaq Composite Index ETF",
        pricing_currency="USD",
        pricing_storage_symbol="proxy:US:NASDAQ_COMP:ONEQ",
        aliases=("纳斯达克", "纳斯达克综合", "纳指", "NASDAQ", "IXIC", "NDX"),
    ),
    "US_NASDAQ100": IndexInstrument(
        symbol="US_NASDAQ100",
        name="Nasdaq 100",
        market="US",
        currency="USD",
        storage_symbol="index:US:NASDAQ100",
        pricing_symbol="QQQ",
        pricing_name="Invesco QQQ Trust",
        pricing_currency="USD",
        pricing_storage_symbol="proxy:US:NASDAQ100:QQQ",
        aliases=("纳斯达克100", "纳指100", "NASDAQ100", "NDX100", "NDX"),
    ),
    "US_DOW": IndexInstrument(
        symbol="US_DOW",
        name="Dow Jones Industrial Average",
        market="US",
        currency="USD",
        storage_symbol="index:US:DOW",
        pricing_symbol="DIA",
        pricing_name="SPDR Dow Jones Industrial Average ETF Trust",
        pricing_currency="USD",
        pricing_storage_symbol="proxy:US:DOW:DIA",
        aliases=("道琼斯", "道指", "DOW", "DJIA", "DJI"),
    ),
    "US_RUSSELL2000": IndexInstrument(
        symbol="US_RUSSELL2000",
        name="Russell 2000",
        market="US",
        currency="USD",
        storage_symbol="index:US:RUSSELL2000",
        pricing_symbol="IWM",
        pricing_name="iShares Russell 2000 ETF",
        pricing_currency="USD",
        pricing_storage_symbol="proxy:US:RUSSELL2000:IWM",
        aliases=("罗素2000", "罗素", "RUSSELL2000", "RUT"),
    ),
    "US_VIX": IndexInstrument(
        symbol="US_VIX",
        name="CBOE Volatility Index",
        market="US",
        currency="USD",
        storage_symbol="index:US:VIX",
        pricing_symbol="VIXY",
        pricing_name="ProShares VIX Short-Term Futures ETF",
        pricing_currency="USD",
        pricing_storage_symbol="proxy:US:VIX:VIXY",
        aliases=("恐慌指数", "波动率指数", "VIX"),
    ),
    "CN_CSI300": IndexInstrument(
        symbol="CN_CSI300",
        name="沪深300",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:CSI300",
        pricing_symbol="sh510300",
        pricing_name="沪深300ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:CSI300:510300",
        aliases=("沪深300", "沪深", "CSI300", "000300"),
    ),
    "CN_CSI_A500": IndexInstrument(
        symbol="CN_CSI_A500",
        name="中证A500",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:CSI_A500",
        pricing_symbol="sh560610",
        pricing_name="A500指数ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:CSI_A500:560610",
        aliases=("中证A500", "中证 A500", "A500", "CSI A500", "CSI_A500", "000510"),
    ),
    "CN_SSE50": IndexInstrument(
        symbol="CN_SSE50",
        name="上证50",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:SSE50",
        pricing_symbol="sh510050",
        pricing_name="上证50ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:SSE50:510050",
        aliases=("上证50", "上证 50", "SSE50", "000016"),
    ),
    "CN_CSI500": IndexInstrument(
        symbol="CN_CSI500",
        name="中证500",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:CSI500",
        pricing_symbol="sh510500",
        pricing_name="中证500ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:CSI500:510500",
        aliases=("中证500", "中证 500", "CSI500", "000905"),
    ),
    "CN_CSI1000": IndexInstrument(
        symbol="CN_CSI1000",
        name="中证1000",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:CSI1000",
        pricing_symbol="sz159845",
        pricing_name="中证1000ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:CSI1000:159845",
        aliases=("中证1000", "中证 1000", "CSI1000", "000852"),
    ),
    "CN_SSE_COMP": IndexInstrument(
        symbol="CN_SSE_COMP",
        name="上证指数",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:SSE_COMP",
        pricing_symbol="sh510210",
        pricing_name="上证综指ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:SSE_COMP:510210",
        aliases=("上证", "上证指数", "上证综指", "SSE Composite", "000001"),
    ),
    "CN_SZSE_COMPONENT": IndexInstrument(
        symbol="CN_SZSE_COMPONENT",
        name="深证成指",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:SZSE_COMPONENT",
        pricing_symbol="sz159903",
        pricing_name="深成ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:SZSE_COMPONENT:159903",
        aliases=("深证", "深证成指", "深成指", "SZSE", "399001"),
    ),
    "CN_CHINEXT": IndexInstrument(
        symbol="CN_CHINEXT",
        name="创业板指",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:CHINEXT",
        pricing_symbol="sz159915",
        pricing_name="创业板ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:CHINEXT:159915",
        aliases=("创业板", "创业板指", "CHINEXT", "399006"),
    ),
    "CN_STAR50": IndexInstrument(
        symbol="CN_STAR50",
        name="科创50",
        market="CN",
        currency="CNY",
        storage_symbol="index:CN:STAR50",
        pricing_symbol="sh588000",
        pricing_name="科创50ETF",
        pricing_currency="CNY",
        pricing_storage_symbol="proxy:CN:STAR50:588000",
        aliases=("科创50", "科创 50", "STAR50", "000688"),
    ),
    "HK_HSI": IndexInstrument(
        symbol="HK_HSI",
        name="恒生指数",
        market="HK",
        currency="HKD",
        storage_symbol="index:HK:HSI",
        pricing_symbol="02800",
        pricing_name="Tracker Fund of Hong Kong",
        pricing_currency="HKD",
        pricing_storage_symbol="proxy:HK:HSI:02800",
        aliases=("恒生", "恒生指数", "HSI"),
    ),
    "HK_HSTECH": IndexInstrument(
        symbol="HK_HSTECH",
        name="恒生科技指数",
        market="HK",
        currency="HKD",
        storage_symbol="index:HK:HSTECH",
        pricing_symbol="03033",
        pricing_name="CSOP Hang Seng TECH Index ETF",
        pricing_currency="HKD",
        pricing_storage_symbol="proxy:HK:HSTECH:03033",
        aliases=("恒生科技", "恒生科技指数", "恒科", "HSTECH"),
    ),
    "HK_HSCEI": IndexInstrument(
        symbol="HK_HSCEI",
        name="恒生中国企业指数",
        market="HK",
        currency="HKD",
        storage_symbol="index:HK:HSCEI",
        pricing_symbol="02828",
        pricing_name="Hang Seng China Enterprises Index ETF",
        pricing_currency="HKD",
        pricing_storage_symbol="proxy:HK:HSCEI:02828",
        aliases=("国企指数", "恒生中国企业", "恒生中国企业指数", "HSCEI", "HSCE"),
    ),
}


def normalize_index_symbol(value: str) -> str:
    return str(value or "").strip().upper()


def get_index_instrument(symbol: str) -> IndexInstrument | None:
    return INDEX_CATALOG.get(normalize_index_symbol(symbol))


def get_supported_index_symbols() -> list[str]:
    return list(INDEX_CATALOG.keys())


__all__ = [
    "INDEX_CATALOG",
    "IndexInstrument",
    "get_index_instrument",
    "get_supported_index_symbols",
    "normalize_index_symbol",
]
