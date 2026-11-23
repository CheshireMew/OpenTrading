from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexSourceBinding:
    eastmoney_secid: str | None = None
    sohu_code: str | None = None
    baostock_code: str | None = None
    sina_hk_symbol: str | None = None
    sina_cn_symbol: str | None = None
    sina_us_symbol: str | None = None
    pricing_provider: str | None = None
    cboe_csv_url: str | None = None
    yfinance_symbol: str | None = None


INDEX_SOURCE_CATALOG: dict[str, IndexSourceBinding] = {
    "US_SP500": IndexSourceBinding(
        pricing_provider="sina_us_etf",
        eastmoney_secid="100.SPX",
        sina_us_symbol=".INX",
        yfinance_symbol="^GSPC",
    ),
    "US_NASDAQ_COMP": IndexSourceBinding(
        pricing_provider="sina_us_etf",
        eastmoney_secid="100.NDX",
        sina_us_symbol=".IXIC",
        yfinance_symbol="^IXIC",
    ),
    "US_NASDAQ100": IndexSourceBinding(
        pricing_provider="sina_us_etf",
        eastmoney_secid="100.NDX100",
        sina_us_symbol=".NDX",
        yfinance_symbol="^NDX",
    ),
    "US_DOW": IndexSourceBinding(
        pricing_provider="sina_us_etf",
        eastmoney_secid="100.DJIA",
        sina_us_symbol=".DJI",
        yfinance_symbol="^DJI",
    ),
    "US_RUSSELL2000": IndexSourceBinding(
        pricing_provider="sina_us_etf",
        cboe_csv_url="https://cdn.cboe.com/api/global/us_indices/daily_prices/RUT_History.csv",
        yfinance_symbol="^RUT",
    ),
    "US_VIX": IndexSourceBinding(
        pricing_provider="sina_us_etf",
        cboe_csv_url="https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
        yfinance_symbol="^VIX",
    ),
    "CN_CSI300": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="1.000300",
        sohu_code="zs_000300",
        baostock_code="sh.000300",
    ),
    "CN_CSI_A500": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="1.000510",
        baostock_code="sh.000510",
        sina_cn_symbol="sh000510",
    ),
    "CN_SSE50": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="1.000016",
        sohu_code="zs_000016",
        baostock_code="sh.000016",
    ),
    "CN_CSI500": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="1.000905",
        sohu_code="zs_000905",
        baostock_code="sh.000905",
    ),
    "CN_CSI1000": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="1.000852",
        sohu_code="zs_000852",
        baostock_code="sh.000852",
    ),
    "CN_SSE_COMP": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="1.000001",
        sohu_code="zs_000001",
        baostock_code="sh.000001",
    ),
    "CN_SZSE_COMPONENT": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="0.399001",
        sohu_code="zs_399001",
        baostock_code="sz.399001",
    ),
    "CN_CHINEXT": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="0.399006",
        sohu_code="zs_399006",
        baostock_code="sz.399006",
    ),
    "CN_STAR50": IndexSourceBinding(
        pricing_provider="sina_cn_etf",
        eastmoney_secid="1.000688",
        sohu_code="zs_000688",
        baostock_code="sh.000688",
    ),
    "HK_HSI": IndexSourceBinding(
        pricing_provider="sina_hk_etf",
        eastmoney_secid="100.HSI",
        sina_hk_symbol="HSI",
        yfinance_symbol="^HSI",
    ),
    "HK_HSTECH": IndexSourceBinding(
        pricing_provider="sina_hk_etf",
        eastmoney_secid="124.HSTECH",
        sina_hk_symbol="HSTECH",
        yfinance_symbol="^HSTECH",
    ),
    "HK_HSCEI": IndexSourceBinding(
        pricing_provider="sina_hk_etf",
        eastmoney_secid="100.HSCEI",
        sina_hk_symbol="HSCEI",
        yfinance_symbol="^HSCE",
    ),
}


def get_index_source_binding(symbol: str) -> IndexSourceBinding:
    return INDEX_SOURCE_CATALOG.get(str(symbol or "").strip().upper(), IndexSourceBinding())


__all__ = ["INDEX_SOURCE_CATALOG", "IndexSourceBinding", "get_index_source_binding"]
