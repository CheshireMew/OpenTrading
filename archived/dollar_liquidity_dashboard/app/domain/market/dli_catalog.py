from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroIndicatorSource:
    fred_id: str | None
    yf_ticker: str | None
    indicator_id: str


@dataclass(frozen=True)
class DliIndicatorDefinition:
    id: str
    label: str
    short_label: str
    group: str
    group_label: str
    weight: float
    polarity: str
    description: str
    unit: str
    is_scored: bool = True


GROUP_WEIGHTS: dict[str, float] = {
    "policy": 65.0,
    "funding": 10.0,
    "credit": 5.0,
    "risk": 20.0,
}

GROUP_DESCRIPTIONS: dict[str, str] = {
    "policy": "Fed 资产负债表、TGA 和 ON RRP 是美元流动性的核心水位。",
    "funding": "SOFR-IORB 利差和 SRF 使用量直接刻画美元融资管道压力。",
    "credit": "银行现金缓冲和信用利差衡量中介体系是否正在收紧。",
    "risk": "VIX、美元指数和 10Y 实际利率作为同期压力背景信号。",
}

DLI_SCORING_DEFINITIONS: tuple[DliIndicatorDefinition, ...] = (
    DliIndicatorDefinition("FED_BALANCE", "美联储资产负债表", "Fed Balance", "policy", "政策与准备金池", 1.0, "lower_tightens", "联储资产端下降代表基础流动性被抽走。", "M USD"),
    DliIndicatorDefinition("TGA", "美国财政部现金账户", "TGA", "policy", "政策与准备金池", 1.0, "higher_tightens", "TGA 上升会从银行体系抽走准备金。", "M USD"),
    DliIndicatorDefinition("ONRRP", "隔夜逆回购", "ON RRP", "policy", "政策与准备金池", 1.0, "higher_tightens", "ON RRP 余额上升代表现金停留在联储设施内。", "B USD"),
    DliIndicatorDefinition("SOFR_IORB", "SOFR-IORB 利差", "SOFR-IORB", "funding", "融资与管道", 1.0, "higher_tightens", "SOFR 相对 IORB 上行代表回购融资压力抬升。", "bp"),
    DliIndicatorDefinition("SRF_USAGE", "SRF 使用量", "SRF Usage", "funding", "融资与管道", 1.0, "higher_tightens", "常备回购工具使用量上升代表市场需要央行回购流动性。", "B USD"),
    DliIndicatorDefinition("BANK_CASH_BUFFER", "银行现金缓冲", "Cash Buffer", "credit", "信用与中介", 1.0, "lower_tightens", "商业银行现金资产占总资产比例下降会削弱中介体系缓冲。", "%"),
    DliIndicatorDefinition("HY_SPREAD", "高收益债利差", "HY Spread", "credit", "信用与中介", 1.0, "higher_tightens", "信用风险溢价扩张代表私人部门融资环境转差。", "%"),
    DliIndicatorDefinition("VIX", "VIX 波动率指数", "VIX", "risk", "风险与价格", 1.0, "higher_tightens", "美股隐含波动率越高，避险和去杠杆压力越强。", ""),
    DliIndicatorDefinition("DXY", "贸易加权美元指数", "Dollar", "risk", "风险与价格", 1.0, "higher_tightens", "美元走强通常压制全球美元流动性。", ""),
    DliIndicatorDefinition("US10Y_REAL", "美国 10 年期实际利率", "10Y Real", "risk", "风险与价格", 1.0, "higher_tightens", "实际利率上行会抬高风险资产估值折现压力。", "%"),
)

DLI_DISPLAY_DEFINITIONS: tuple[DliIndicatorDefinition, ...] = DLI_SCORING_DEFINITIONS + (
    DliIndicatorDefinition("NET_LIQUIDITY", "净流动性", "Net Liquidity", "policy", "补充观察", 0.0, "lower_tightens", "Fed 总资产减 TGA 与 ON RRP 后的观察项，不纳入 DLI 综合评分。", "M USD", False),
    DliIndicatorDefinition("M2", "美国 M2 货币供应", "M2", "risk", "补充观察", 0.0, "lower_tightens", "广义货币环境观察项，不纳入 DLI 综合评分。", "B USD", False),
)

DLI_DEFINITION_BY_ID = {item.id: item for item in DLI_DISPLAY_DEFINITIONS}
DLI_SCORING_IDS = tuple(item.id for item in DLI_SCORING_DEFINITIONS)
DLI_VISIBLE_IDS = tuple(item.id for item in DLI_DISPLAY_DEFINITIONS)

MACRO_INDICATOR_SOURCES: tuple[MacroIndicatorSource, ...] = (
    MacroIndicatorSource("DGS10", "^TNX", "US10Y"),
    MacroIndicatorSource("DGS2", None, "US02Y"),
    MacroIndicatorSource("NASDAQCOM", "^IXIC", "NASDAQ"),
    MacroIndicatorSource("BAMLH0A0HYM2", None, "HY_SPREAD"),
    MacroIndicatorSource("FEDFUNDS", None, "FED_RATE"),
    MacroIndicatorSource("IORB", None, "IORB"),
    MacroIndicatorSource("WALCL", None, "FED_BALANCE"),
    MacroIndicatorSource(None, None, "TGA"),
    MacroIndicatorSource("RRPONTSYD", None, "ONRRP"),
    MacroIndicatorSource("RPONTSYD", None, "RPONTSYD"),
    MacroIndicatorSource("CASACBW027SBOG", None, "CASACBW027SBOG"),
    MacroIndicatorSource("TLAACBW027SBOG", None, "TLAACBW027SBOG"),
    MacroIndicatorSource("SOFR", None, "SOFR"),
    MacroIndicatorSource("DFII10", None, "DFII10"),
    MacroIndicatorSource("M2SL", None, "M2"),
    MacroIndicatorSource("VIXCLS", "^VIX", "VIX"),
    MacroIndicatorSource("DTWEXBGS", None, "DXY"),
    MacroIndicatorSource("DCOILWTICO", "CL=F", "WTI"),
)

DERIVED_DLI_SOURCE_IDS = (
    "SOFR",
    "IORB",
    "RPONTSYD",
    "CASACBW027SBOG",
    "TLAACBW027SBOG",
    "DFII10",
    "FED_BALANCE",
    "TGA",
    "ONRRP",
)
DLI_SOURCE_IDS = tuple(sorted(set(DLI_VISIBLE_IDS) | set(DERIVED_DLI_SOURCE_IDS)))

_BASE_MARKET_META: dict[str, tuple[str, str, str]] = {
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

_RAW_DLI_META: dict[str, tuple[str, str, str]] = {
    "IORB": ("Interest on Reserve Balances", "Macro", "%"),
    "RPONTSYD": ("Overnight Repo Purchases", "Macro", "B USD"),
    "CASACBW027SBOG": ("Cash Assets, All Commercial Banks", "Macro", "B USD"),
    "TLAACBW027SBOG": ("Total Assets, All Commercial Banks", "Macro", "B USD"),
    "SOFR": ("Secured Overnight Financing Rate", "Macro", "%"),
    "DFII10": ("10Y Treasury Real Yield", "Macro", "%"),
}


def market_indicator_meta_catalog() -> dict[str, tuple[str, str, str]]:
    catalog = dict(_BASE_MARKET_META)
    catalog.update(_RAW_DLI_META)
    catalog.update({definition.id: (definition.short_label, "Macro", definition.unit) for definition in DLI_DISPLAY_DEFINITIONS})
    return catalog
