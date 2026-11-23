from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiquidityIndicatorDefinition:
    indicator_id: str
    name: str
    short_label: str
    group_id: str
    group_label: str
    raw_weight: float
    polarity: str
    description: str
    unit: str
    provider: str
    provider_series_id: str | None = None
    frequency: str = "daily"
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
    "risk": "VIX、美元指数和 10 年期实际利率作为同期压力背景信号。",
}

PRESSURE_PERCENTILES: dict[str, float] = {
    "support": 20.0,
    "neutral": 50.0,
    "pressure": 80.0,
}

FRESHNESS_DAYS_BY_FREQUENCY: dict[str, int] = {
    "daily": 4,
    "weekly": 10,
    "monthly": 40,
}


SCORED_DEFINITIONS: tuple[LiquidityIndicatorDefinition, ...] = (
    LiquidityIndicatorDefinition(
        "FED_BALANCE", "美联储资产负债表", "Fed Balance", "policy", "政策与准备金池",
        1.0, "lower_tightens", "联储资产端下降代表基础流动性被抽走。", "M USD",
        "fred", "WALCL", "weekly",
    ),
    LiquidityIndicatorDefinition(
        "TGA", "美国财政部现金账户", "TGA", "policy", "政策与准备金池",
        1.0, "higher_tightens", "TGA 上升会从银行体系抽走准备金。", "M USD",
        "treasury", None, "daily",
    ),
    LiquidityIndicatorDefinition(
        "ONRRP", "隔夜逆回购", "ON RRP", "policy", "政策与准备金池",
        1.0, "higher_tightens", "ON RRP 余额上升代表现金停留在联储设施内。", "B USD",
        "fred", "RRPONTSYD", "daily",
    ),
    LiquidityIndicatorDefinition(
        "SOFR_IORB", "SOFR-IORB 利差", "SOFR-IORB", "funding", "融资与管道",
        1.0, "higher_tightens", "SOFR 相对 IORB 上行代表回购融资压力抬升。", "bp",
        "derived", None, "daily",
    ),
    LiquidityIndicatorDefinition(
        "SRF_USAGE", "SRF 使用量", "SRF Usage", "funding", "融资与管道",
        1.0, "higher_tightens", "常备回购工具使用量上升代表市场需要央行回购流动性。", "B USD",
        "derived", None, "daily",
    ),
    LiquidityIndicatorDefinition(
        "BANK_CASH_BUFFER", "银行现金缓冲", "Cash Buffer", "credit", "信用与中介",
        1.0, "lower_tightens", "商业银行现金资产占总资产比例下降会削弱中介体系缓冲。", "%",
        "derived", None, "weekly",
    ),
    LiquidityIndicatorDefinition(
        "HY_SPREAD", "高收益债利差", "HY Spread", "credit", "信用与中介",
        1.0, "higher_tightens", "信用风险溢价扩张代表私人部门融资环境转差。", "%",
        "fred", "BAMLH0A0HYM2", "daily",
    ),
    LiquidityIndicatorDefinition(
        "VIX", "VIX 波动率指数", "VIX", "risk", "风险与价格",
        1.0, "higher_tightens", "美股隐含波动率越高，避险和去杠杆压力越强。", "",
        "fred", "VIXCLS", "daily",
    ),
    LiquidityIndicatorDefinition(
        "DXY", "贸易加权美元指数", "Dollar", "risk", "风险与价格",
        1.0, "higher_tightens", "美元走强通常压制全球美元流动性。", "",
        "fred", "DTWEXBGS", "daily",
    ),
    LiquidityIndicatorDefinition(
        "US10Y_REAL", "美国 10 年期实际利率", "10Y Real", "risk", "风险与价格",
        1.0, "higher_tightens", "实际利率上行会抬高风险资产估值折现压力。", "%",
        "derived", None, "daily",
    ),
)

DISPLAY_DEFINITIONS: tuple[LiquidityIndicatorDefinition, ...] = SCORED_DEFINITIONS + (
    LiquidityIndicatorDefinition(
        "NET_LIQUIDITY", "净流动性", "Net Liquidity", "policy", "补充观察",
        0.0, "lower_tightens", "Fed 总资产减 TGA 与 ON RRP 后的观察项，不纳入综合评分。", "M USD",
        "derived", None, "daily", False,
    ),
    LiquidityIndicatorDefinition(
        "M2", "美国 M2 货币供应", "M2", "risk", "补充观察",
        0.0, "lower_tightens", "广义货币环境观察项，不纳入综合评分。", "B USD",
        "fred", "M2SL", "monthly", False,
    ),
)

RAW_SOURCE_DEFINITIONS: tuple[LiquidityIndicatorDefinition, ...] = (
    LiquidityIndicatorDefinition("SOFR", "有担保隔夜融资利率", "SOFR", "source", "原始输入", 0, "higher_tightens", "SOFR-IORB 的原始输入。", "%", "fred", "SOFR", "daily", False),
    LiquidityIndicatorDefinition("IORB", "准备金余额利率", "IORB", "source", "原始输入", 0, "higher_tightens", "SOFR-IORB 的原始输入。", "%", "fred", "IORB", "daily", False),
    LiquidityIndicatorDefinition("RPONTSYD", "常备回购操作", "SRF Raw", "source", "原始输入", 0, "higher_tightens", "SRF 使用量的原始输入。", "B USD", "fred", "RPONTSYD", "daily", False),
    LiquidityIndicatorDefinition("CASACBW027SBOG", "商业银行现金资产", "Bank Cash", "source", "原始输入", 0, "lower_tightens", "银行现金缓冲的分子。", "B USD", "fred", "CASACBW027SBOG", "weekly", False),
    LiquidityIndicatorDefinition("TLAACBW027SBOG", "商业银行总资产", "Bank Assets", "source", "原始输入", 0, "lower_tightens", "银行现金缓冲的分母。", "B USD", "fred", "TLAACBW027SBOG", "weekly", False),
    LiquidityIndicatorDefinition("DFII10", "10 年期实际利率", "10Y Real Raw", "source", "原始输入", 0, "higher_tightens", "实际利率的原始输入。", "%", "fred", "DFII10", "daily", False),
)

DEFINITION_BY_ID = {item.indicator_id: item for item in DISPLAY_DEFINITIONS}
SCORED_IDS = tuple(item.indicator_id for item in SCORED_DEFINITIONS)
SOURCE_DEFINITIONS = tuple(
    item
    for item in (*DISPLAY_DEFINITIONS, *RAW_SOURCE_DEFINITIONS)
    if item.provider in {"fred", "treasury"}
)
SOURCE_IDS = tuple(dict.fromkeys(item.indicator_id for item in SOURCE_DEFINITIONS))
