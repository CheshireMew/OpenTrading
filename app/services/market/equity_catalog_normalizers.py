"""Normalize exchange identifiers before joining stock exposure across venues.

Listings come from exchange catalogs, never from the display-name dictionaries.
Equity ETFs stay separate from the stocks they track (e.g. NVDL != NVDA).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from app.contracts.dto.equity_catalog import EquityCatalogItemResponse, EquityOfferingResponse
from app.services.market.equity_logo_overrides import LOCAL_EQUITY_LOGOS


_REFERRAL_PARAMETERS = {
    "binance.com": ("ref", "SRXT5KUM"),
    "okx.com": ("channelId", "A999998"),
    "bitget.com": ("clacCode", "W76TDL38"),
}


def equity_referral_url(url: str) -> str:
    """Attach the owner's invitation to outbound pages, including cached listings."""
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    referral = _REFERRAL_PARAMETERS.get(host)
    if not referral or parts.scheme not in {"https", "http"} or parts.path.startswith(("/api/", "/bapi/")):
        return url
    key, code = referral
    query = [(name, value) for name, value in parse_qsl(parts.query, keep_blank_values=True)
             if name.lower() != key.lower()]
    query.append((key, code))
    return urlunsplit(parts._replace(query=urlencode(query)))


CHINESE_NAMES = {
    "AAPL": "苹果", "MSFT": "微软", "NVDA": "英伟达", "TSLA": "特斯拉",
    "GOOGL": "谷歌", "GOOG": "谷歌", "AMZN": "亚马逊", "META": "Meta",
    "AMD": "超威半导体", "INTC": "英特尔", "MU": "美光", "AVGO": "博通",
    "QCOM": "高通", "TSM": "台积电", "ASML": "阿斯麦", "AMAT": "应用材料",
    "SNDK": "闪迪", "WDC": "西部数据", "STX": "希捷", "DELL": "戴尔",
    "SMCI": "超微电脑", "ORCL": "甲骨文", "NFLX": "奈飞", "ADBE": "Adobe",
    "PLTR": "帕兰提尔", "CRWV": "CoreWeave", "NBIS": "Nebius",
    "COIN": "Coinbase", "MSTR": "Strategy 微策略", "HOOD": "Robinhood",
    "CRCL": "Circle", "JPM": "摩根大通", "GS": "高盛", "BRK.B": "伯克希尔 B",
    "BABA": "阿里巴巴", "PDD": "拼多多", "BIDU": "百度", "BILI": "哔哩哔哩",
    "JD": "京东", "NIO": "蔚来", "XPEV": "小鹏汽车", "LI": "理想汽车",
    "KO": "可口可乐", "COST": "好市多", "WMT": "沃尔玛", "MCD": "麦当劳",
    "LLY": "礼来", "UNH": "联合健康", "PFE": "辉瑞", "NVO": "诺和诺德",
    "RKLB": "Rocket Lab", "ASTS": "AST SpaceMobile", "SPCX": "SpaceX",
    "SPY": "标普 500 ETF", "QQQ": "纳斯达克 100 ETF", "IWM": "罗素 2000 ETF",
    "SMH": "半导体 ETF", "SOXL": "三倍做多半导体 ETF", "SOXS": "三倍做空半导体 ETF",
    "TQQQ": "三倍做多纳指 ETF", "SQQQ": "三倍做空纳指 ETF", "EWY": "韩国股票 ETF",
}

# Identifiers that differ across official exchange catalogs.
TICKER_ALIASES = {
    "BRKB": "BRK.B", "BRK-B": "BRK.B", "BRK/B": "BRK.B",
    "BRKA": "BRK.A", "BRK-A": "BRK.A", "BRK/A": "BRK.A",
    "STXSTOCK": "STX", "QNTX": "QNT",
    "HK1810": "XIAOMI", "HK0700": "TENCENT",
}
NON_US_MARKETS = {
    "XIAOMI": "HK", "TENCENT": "HK", "POPMART": "HK", "MINIMAX": "HK",
    "ZHIPU": "HK", "MEITUAN": "HK", "KUAISHOU": "HK", "BYD": "HK",
    "GIGADEV": "HK", "ZHONGJI": "HK", "HK0625": "HK", "HK0992": "HK",
    "CSOPSKHYNIX2L": "HK", "CSOPSAMSUNG2L": "HK",
    "SKHYNIX": "KR", "SAMSUNG": "KR", "HYUNDAI": "KR", "SAMSUNGEM": "KR", "HANMI": "KR",
    "LGELECTRONICS": "KR", "NAVER": "KR", "KODEX200": "KR", "KR200": "KR",
    "KIOXIA": "JP", "SOFTBANK": "JP", "JP225": "JP",
    "CXMT": "CN", "UNITREE": "CN", "MOONSHOT": "CN",
}
INDEX_TICKERS = {"US100", "US500", "JP225", "KR200"}

# Stock feeds also contain gold, oil, bond and volatility products. These do not
# provide equity exposure, even though the exchange may put them in a stocks tab.
NON_EQUITY_FUNDS = {
    "AAAU", "GLD", "GLDM", "IAU", "SLV", "SIVR", "PALL", "PPLT", "GLTR",
    "USO", "BNO", "UNG", "BOIL", "KOLD", "UCO", "SCO", "UVXY", "VXX", "VIXY",
    "SVXY", "UVIX", "SVIX", "TLT", "TLH", "IEF", "SHY", "BIL", "SGOV", "SHV",
    "TMF", "TMV", "TBT", "TBX", "GOVT", "AGG", "BND", "BNDX", "TIP", "LQD",
    "HYG", "JNK", "MUB", "MINT", "JPST", "IBIT", "FBTC", "BITO", "BITI", "BITX",
    "BTC", "ETHA", "ETHE", "ETH", "GBTC", "ARKB", "HODL", "BTCO", "EZBC",
    "FETH", "ETHW", "ETHU", "ETHT", "USFR", "TFLO", "SPHY", "BWET",
}
NON_EQUITY_NAME = re.compile(
    r"(?:physical (?:gold|silver|platinum|palladium)|gold (?:trust|shares)|silver (?:trust|shares)|"
    r"(?:treasury|bond|fixed income|money market|vix|volatility)\b|"
    r"(?:bitcoin|ethereum|ether|crypto|crude oil|natural gas) (?:trust|fund|etf)|"
    r"(?:oil|commodity|commodities) (?:fund|futures)|ultra bloomberg)", re.I,
)


def canonical_ticker(value: str) -> str:
    ticker = str(value).strip().upper()
    if ticker.startswith("EQ_"):
        ticker = ticker[3:]
    if ticker.endswith(".US"):
        ticker = ticker[:-3]
    return TICKER_ALIASES.get(ticker, ticker)


def clean_name(value: str) -> str:
    return re.sub(r"\s*(?:\((?:bStocks|Ondo|xStock|xStocks)\)|（bStocks）|\(bStocks）)\s*", "", str(value), flags=re.I).strip()


def equity_exposure(ticker: str, name: str, asset_type: str) -> bool:
    if not ticker or ticker in {"TESTA", "TEST", "XTESTA"}:
        return False
    # A real company such as MUB (Micron's token) must be unwrapped to MU first.
    if ticker in NON_EQUITY_FUNDS:
        return False
    return not (asset_type in {"etf", "unknown"} and NON_EQUITY_NAME.search(name))


def make_listing(*, ticker: str, name: str, platform: str, trading_type: str,
                 product: str, symbol: str, quote_currency: str, source_id: str,
                 status: str = "trading", market: str = "", asset_type: str = "unknown",
                 url: str = "", logo_url: str | None = None) -> dict:
    ticker = canonical_ticker(ticker)
    if ticker in INDEX_TICKERS:
        asset_type = "index"
    elif asset_type not in {"stock", "etf", "index"}:
        asset_type = "etf" if re.search(r"\b(?:ETF|ETN|fund|trust)\b", name, re.I) else "unknown"
    return {
        "ticker": ticker, "name": clean_name(name) or ticker, "asset_type": asset_type,
        "logo_url": logo_url,
        "market": market or NON_US_MARKETS.get(ticker, "US"),
        "offering": dict(source_id=source_id, platform=platform, trading_type=trading_type,
                         product=product, symbol=symbol, quote=quote_currency, status=status, url=url),
    }


def merge_listings(listings: list[dict], metadata: list[dict]) -> list[EquityCatalogItemResponse]:
    meta: dict[str, dict] = {}
    for row in metadata:
        ticker = canonical_ticker(row["ticker"])
        previous = meta.setdefault(ticker, dict(row))
        if previous.get("asset_type", "unknown") == "unknown" and row.get("asset_type") != "unknown":
            previous["asset_type"] = row["asset_type"]
        if not previous.get("logo_url") and row.get("logo_url"):
            previous["logo_url"] = row["logo_url"]
    grouped: dict[str, EquityCatalogItemResponse] = {}
    seen: set[tuple[str, str]] = set()
    for row in listings:
        ticker = row["ticker"]
        details = meta.get(ticker, {})
        name = details.get("name") or row["name"]
        kind = details.get("asset_type") or row["asset_type"]
        if not equity_exposure(ticker, name, kind):
            continue
        item = grouped.get(ticker)
        if item is None:
            item = EquityCatalogItemResponse(
                ticker=ticker, name=name, name_zh=CHINESE_NAMES.get(ticker, ""),
                logo_url=LOCAL_EQUITY_LOGOS.get(ticker) or details.get("logo_url") or row.get("logo_url") or None,
                asset_type=kind, market=NON_US_MARKETS.get(ticker, row["market"]),
                platforms=[], trading_types=[], offerings=[],
            )
            grouped[ticker] = item
        elif item.name == ticker and name != ticker:
            item.name = name
        if not item.logo_url and row.get("logo_url"):
            item.logo_url = row["logo_url"]
        if item.asset_type == "unknown" and kind != "unknown":
            item.asset_type = kind
        offering = EquityOfferingResponse(**row["offering"])
        offering.url = equity_referral_url(offering.url)
        key = (offering.source_id, offering.symbol)
        if key not in seen:
            seen.add(key)
            item.offerings.append(offering)
    for item in grouped.values():
        item.offerings.sort(key=lambda o: (o.platform, o.trading_type, o.product, o.symbol))
        item.platforms = sorted({o.platform for o in item.offerings})
        item.trading_types = sorted({o.trading_type for o in item.offerings})
    return sorted(grouped.values(), key=lambda item: (-len(item.platforms), item.ticker))


def trade_url(platform: str, trading_type: str, symbol: str) -> str:
    symbol = quote(symbol, safe="-_.")
    if platform == "okx":
        return f"https://www.okx.com/trade-{'spot' if trading_type == 'spot' else 'swap'}/{symbol.lower()}"
    if platform == "bitget":
        return f"https://www.bitget.com/{'spot' if trading_type == 'spot' else 'futures/usdt'}/{symbol}"
    return f"https://www.binance.com/en/{'trade' if trading_type == 'spot' else 'futures'}/{symbol}"
