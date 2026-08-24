from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
import talib.abstract as ta


WarmupFn = Callable[[dict[str, Any]], int]
ApplyFn = Callable[[pd.DataFrame, str, dict[str, Any]], None]
RenderFn = Callable[[str, str, dict[str, Any]], list[str]]


def _int(params: dict[str, Any], key: str, default: int) -> int:
    return int(params.get(key, default))


def _float(params: dict[str, Any], key: str, default: float) -> float:
    return float(params.get(key, default))


@dataclass(frozen=True)
class IndicatorEngineDefinition:
    key: str
    name: str
    description: str
    outputs: tuple[dict[str, Any], ...]
    params: tuple[dict[str, Any], ...]
    warmup: WarmupFn
    apply: ApplyFn
    render_code: RenderFn

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "engine": self.key,
            "name": self.name,
            "description": self.description,
            "outputs": deepcopy(list(self.outputs)),
            "params": deepcopy(list(self.params)),
        }

    def output_columns(self, indicator_id: str) -> list[str]:
        return [f'{indicator_id}__{output.get("key", "value")}' for output in self.outputs]


def _single_output(label: str) -> tuple[dict[str, Any], ...]:
    return ({"key": "value", "label": label},)


def _period_param(default: int, min_value: int, max_value: int, label: str = "周期") -> tuple[dict[str, Any], ...]:
    return ({"key": "period", "label": label, "type": "int", "default": default, "min": min_value, "max": max_value, "step": 1},)


def _ema_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = ta.EMA(frame, timeperiod=_int(params, "period", 20))


def _ema_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = ta.EMA({frame_var}, timeperiod={_int(params, "period", 20)})']


def _sma_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = ta.SMA(frame, timeperiod=_int(params, "period", 20))


def _sma_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = ta.SMA({frame_var}, timeperiod={_int(params, "period", 20)})']


def _rsi_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = ta.RSI(frame, timeperiod=_int(params, "period", 14))


def _rsi_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = ta.RSI({frame_var}, timeperiod={_int(params, "period", 14)})']


def _macd_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    result = ta.MACD(frame, fastperiod=_int(params, "fast", 12), slowperiod=_int(params, "slow", 26), signalperiod=_int(params, "signal", 9))
    frame[f"{indicator_id}__macd"] = result["macd"]
    frame[f"{indicator_id}__signal"] = result["macdsignal"]
    frame[f"{indicator_id}__hist"] = result["macdhist"]


def _macd_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [
        f'        {indicator_id}_macd = ta.MACD({frame_var}, fastperiod={_int(params, "fast", 12)}, slowperiod={_int(params, "slow", 26)}, signalperiod={_int(params, "signal", 9)})',
        f'        {frame_var}["{indicator_id}__macd"] = {indicator_id}_macd["macd"]',
        f'        {frame_var}["{indicator_id}__signal"] = {indicator_id}_macd["macdsignal"]',
        f'        {frame_var}["{indicator_id}__hist"] = {indicator_id}_macd["macdhist"]',
    ]


def _bbands_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    stddev = _float(params, "stddev", 2.0)
    upper, middle, lower = ta.BBANDS(frame["close"], timeperiod=_int(params, "period", 20), nbdevup=stddev, nbdevdn=stddev, matype=0)
    frame[f"{indicator_id}__upper"] = upper
    frame[f"{indicator_id}__middle"] = middle
    frame[f"{indicator_id}__lower"] = lower


def _bbands_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [
        f'        {indicator_id}_upper, {indicator_id}_middle, {indicator_id}_lower = ta.BBANDS({frame_var}["close"], timeperiod={_int(params, "period", 20)}, nbdevup={_float(params, "stddev", 2.0)}, nbdevdn={_float(params, "stddev", 2.0)}, matype=0)',
        f'        {frame_var}["{indicator_id}__upper"] = {indicator_id}_upper',
        f'        {frame_var}["{indicator_id}__middle"] = {indicator_id}_middle',
        f'        {frame_var}["{indicator_id}__lower"] = {indicator_id}_lower',
    ]


def _volume_sma_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = ta.SMA(frame["volume"], timeperiod=_int(params, "period", 20))


def _volume_sma_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = ta.SMA({frame_var}["volume"], timeperiod={_int(params, "period", 20)})']


def _atr_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = ta.ATR(frame, timeperiod=_int(params, "period", 14))


def _atr_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = ta.ATR({frame_var}, timeperiod={_int(params, "period", 14)})']


def _rolling_high_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = frame["high"].rolling(_int(params, "lookback", 20)).max().shift(1)


def _rolling_high_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = {frame_var}["high"].rolling({_int(params, "lookback", 20)}).max().shift(1)']


def _rolling_low_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = frame["low"].rolling(_int(params, "lookback", 20)).min().shift(1)


def _rolling_low_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = {frame_var}["low"].rolling({_int(params, "lookback", 20)}).min().shift(1)']


def _roc_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    frame[f"{indicator_id}__value"] = ta.ROC(frame, timeperiod=_int(params, "period", 12))


def _roc_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    return [f'        {frame_var}["{indicator_id}__value"] = ta.ROC({frame_var}, timeperiod={_int(params, "period", 12)})']


def _displacement_atr_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    lookback = _int(params, "lookback", 24)
    atr = ta.ATR(frame, timeperiod=_int(params, "atr_period", 14))
    frame[f"{indicator_id}__value"] = (frame["close"] - frame["close"].shift(lookback)) / atr.replace(0.0, pd.NA)


def _displacement_atr_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    lookback = _int(params, "lookback", 24)
    atr_period = _int(params, "atr_period", 14)
    return [
        f'        {indicator_id}_atr = ta.ATR({frame_var}, timeperiod={atr_period})',
        f'        {frame_var}["{indicator_id}__value"] = ({frame_var}["close"] - {frame_var}["close"].shift({lookback})) / {indicator_id}_atr.replace(0.0, pd.NA)',
    ]


def _efficiency_ratio_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    lookback = _int(params, "lookback", 24)
    displacement = (frame["close"] - frame["close"].shift(lookback)).abs()
    path = frame["close"].diff().abs().rolling(lookback).sum()
    frame[f"{indicator_id}__value"] = displacement / path.replace(0.0, pd.NA)


def _efficiency_ratio_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    lookback = _int(params, "lookback", 24)
    return [
        f'        {indicator_id}_displacement = ({frame_var}["close"] - {frame_var}["close"].shift({lookback})).abs()',
        f'        {indicator_id}_path = {frame_var}["close"].diff().abs().rolling({lookback}).sum()',
        f'        {frame_var}["{indicator_id}__value"] = {indicator_id}_displacement / {indicator_id}_path.replace(0.0, pd.NA)',
    ]


def _range_context_apply(frame: pd.DataFrame, indicator_id: str, params: dict[str, Any]) -> None:
    lookback = _int(params, "lookback", 32)
    upper = frame["high"].rolling(lookback).max().shift(1)
    lower = frame["low"].rolling(lookback).min().shift(1)
    width = upper - lower
    atr = ta.ATR(frame, timeperiod=_int(params, "atr_period", 14))
    frame[f"{indicator_id}__upper"] = upper
    frame[f"{indicator_id}__lower"] = lower
    frame[f"{indicator_id}__middle"] = (upper + lower) / 2.0
    frame[f"{indicator_id}__position"] = (frame["close"] - lower) / width.replace(0.0, pd.NA)
    frame[f"{indicator_id}__width_ratio"] = width / atr.replace(0.0, pd.NA)


def _range_context_render(frame_var: str, indicator_id: str, params: dict[str, Any]) -> list[str]:
    lookback = _int(params, "lookback", 32)
    atr_period = _int(params, "atr_period", 14)
    return [
        f'        {frame_var}["{indicator_id}__upper"] = {frame_var}["high"].rolling({lookback}).max().shift(1)',
        f'        {frame_var}["{indicator_id}__lower"] = {frame_var}["low"].rolling({lookback}).min().shift(1)',
        f'        {frame_var}["{indicator_id}__middle"] = ({frame_var}["{indicator_id}__upper"] + {frame_var}["{indicator_id}__lower"]) / 2.0',
        f'        {indicator_id}_width = {frame_var}["{indicator_id}__upper"] - {frame_var}["{indicator_id}__lower"]',
        f'        {indicator_id}_atr = ta.ATR({frame_var}, timeperiod={atr_period})',
        f'        {frame_var}["{indicator_id}__position"] = ({frame_var}["close"] - {frame_var}["{indicator_id}__lower"]) / {indicator_id}_width.replace(0.0, pd.NA)',
        f'        {frame_var}["{indicator_id}__width_ratio"] = {indicator_id}_width / {indicator_id}_atr.replace(0.0, pd.NA)',
    ]


INDICATOR_ENGINES: dict[str, IndicatorEngineDefinition] = {
    "ema": IndicatorEngineDefinition("ema", "EMA", "指数移动平均线", _single_output("EMA"), _period_param(20, 5, 200), lambda params: _int(params, "period", 20), _ema_apply, _ema_render),
    "sma": IndicatorEngineDefinition("sma", "SMA", "简单移动平均线", _single_output("SMA"), _period_param(20, 5, 200), lambda params: _int(params, "period", 20), _sma_apply, _sma_render),
    "rsi": IndicatorEngineDefinition("rsi", "RSI", "相对强弱指标", _single_output("RSI"), _period_param(14, 5, 50), lambda params: _int(params, "period", 14), _rsi_apply, _rsi_render),
    "macd": IndicatorEngineDefinition(
        "macd",
        "MACD",
        "MACD 动量指标",
        ({"key": "macd", "label": "MACD"}, {"key": "signal", "label": "Signal"}, {"key": "hist", "label": "Hist"}),
        (
            {"key": "fast", "label": "快线", "type": "int", "default": 12, "min": 2, "max": 50, "step": 1},
            {"key": "slow", "label": "慢线", "type": "int", "default": 26, "min": 5, "max": 100, "step": 1},
            {"key": "signal", "label": "信号线", "type": "int", "default": 9, "min": 2, "max": 50, "step": 1},
        ),
        lambda params: _int(params, "slow", 26) + _int(params, "signal", 9),
        _macd_apply,
        _macd_render,
    ),
    "bbands": IndicatorEngineDefinition(
        "bbands",
        "Bollinger Bands",
        "布林带",
        ({"key": "upper", "label": "上轨"}, {"key": "middle", "label": "中轨"}, {"key": "lower", "label": "下轨"}),
        (
            {"key": "period", "label": "周期", "type": "int", "default": 20, "min": 5, "max": 100, "step": 1},
            {"key": "stddev", "label": "标准差", "type": "float", "default": 2.0, "min": 0.5, "max": 4.0, "step": 0.1},
        ),
        lambda params: _int(params, "period", 20),
        _bbands_apply,
        _bbands_render,
    ),
    "volume_sma": IndicatorEngineDefinition("volume_sma", "Volume SMA", "成交量均线", _single_output("量均线"), _period_param(20, 5, 120), lambda params: _int(params, "period", 20), _volume_sma_apply, _volume_sma_render),
    "atr": IndicatorEngineDefinition("atr", "ATR", "平均真实波幅", _single_output("ATR"), _period_param(14, 5, 100), lambda params: _int(params, "period", 14), _atr_apply, _atr_render),
    "rolling_high": IndicatorEngineDefinition("rolling_high", "Rolling High", "滚动最高价", _single_output("突破高点"), ({"key": "lookback", "label": "回看周期", "type": "int", "default": 20, "min": 5, "max": 120, "step": 1},), lambda params: _int(params, "lookback", 20), _rolling_high_apply, _rolling_high_render),
    "rolling_low": IndicatorEngineDefinition("rolling_low", "Rolling Low", "滚动最低价", _single_output("支撑低点"), ({"key": "lookback", "label": "回看周期", "type": "int", "default": 20, "min": 5, "max": 120, "step": 1},), lambda params: _int(params, "lookback", 20), _rolling_low_apply, _rolling_low_render),
    "roc": IndicatorEngineDefinition("roc", "ROC", "价格变化率", _single_output("ROC"), _period_param(12, 2, 120), lambda params: _int(params, "period", 12), _roc_apply, _roc_render),
    "displacement_atr": IndicatorEngineDefinition(
        "displacement_atr",
        "Displacement / ATR",
        "用 ATR 归一化后的净位移，适合做趋势状态强度 M。",
        _single_output("M"),
        (
            {"key": "lookback", "label": "位移窗口", "type": "int", "default": 24, "min": 4, "max": 240, "step": 1},
            {"key": "atr_period", "label": "ATR 周期", "type": "int", "default": 14, "min": 5, "max": 100, "step": 1},
        ),
        lambda params: max(_int(params, "lookback", 24), _int(params, "atr_period", 14)),
        _displacement_atr_apply,
        _displacement_atr_render,
    ),
    "efficiency_ratio": IndicatorEngineDefinition("efficiency_ratio", "Efficiency Ratio", "净位移除以滚动路径长度，适合做趋势效率 E。", _single_output("E"), ({"key": "lookback", "label": "效率窗口", "type": "int", "default": 24, "min": 4, "max": 240, "step": 1},), lambda params: _int(params, "lookback", 24) + 1, _efficiency_ratio_apply, _efficiency_ratio_render),
    "range_context": IndicatorEngineDefinition(
        "range_context",
        "Range Context",
        "输出区间上下沿、中轴、位置百分比和区间宽度，适合做 P 和宽度过滤。",
        (
            {"key": "upper", "label": "区间上沿"},
            {"key": "lower", "label": "区间下沿"},
            {"key": "middle", "label": "区间中轴"},
            {"key": "position", "label": "P"},
            {"key": "width_ratio", "label": "宽度 / ATR"},
        ),
        (
            {"key": "lookback", "label": "区间窗口", "type": "int", "default": 32, "min": 8, "max": 240, "step": 1},
            {"key": "atr_period", "label": "ATR 周期", "type": "int", "default": 14, "min": 5, "max": 100, "step": 1},
        ),
        lambda params: max(_int(params, "lookback", 32), _int(params, "atr_period", 14)),
        _range_context_apply,
        _range_context_render,
    ),
}


def indicator_engine_catalog() -> dict[str, dict[str, Any]]:
    return {
        key: definition.catalog_entry()
        for key, definition in INDICATOR_ENGINES.items()
    }


def indicator_engine_definition(indicator_type: str, indicator_spec: dict[str, Any]) -> IndicatorEngineDefinition:
    engine = str(indicator_spec.get("engine") or indicator_type)
    definition = INDICATOR_ENGINES.get(engine)
    if definition is None:
        raise ValueError(f"不支持的指标引擎: {engine}")
    return definition


