from __future__ import annotations

import inspect
import textwrap
from typing import Any

import numpy as np
import pandas as pd
import talib.abstract as ta

from app.domain.backtest.freqtrade_exit_codegen import render_threshold_custom_exit
from app.domain.backtest.freqtrade_strategy_runtime import (
    render_freqtrade_strategy_runtime,
    resolve_freqtrade_strategy_runtime,
)

TEMPLATE_KEY = "btc_regime_pulse_supertrend"
RUNTIME_CONTRACT: dict[str, Any] = {
    "builder_kind": "scripted",
    "capabilities": {
        "paper": True,
        "version_editing": False,
    },
}
WARMUP_BARS = 220

BTC_REGIME_PULSE_SUPERTREND_PARAMS: dict[str, Any] = {
    "atr_length": 10,
    "base_multiplier": 3.0,
    "regime_lookback": 40,
    "adx_length": 14,
    "adx_threshold": 20,
    "trend_ema_length": 50,
    "volume_ma_length": 20,
    "min_signal_score": 65,
    "cooldown_bars": 5,
    "stoploss_atr_multiplier": 6.0,
    "takeprofit_rr": 2.5,
}


def build_signal_frame(candles: list[list[float]], timeframe: str) -> pd.DataFrame:
    return _build_signal_frame_from_candles(candles, timeframe)


def build_strategy_code(*, strategy_class_name: str, timeframe: str) -> str:
    return _build_btc_regime_pulse_supertrend(strategy_class_name, timeframe)


def warmup_bars(_config: dict[str, Any], _timeframe: str) -> int:
    return WARMUP_BARS


def trade_settings(_config: dict[str, Any]) -> dict[str, Any]:
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    return {
        "order_types": order_types,
        "position_adjustment_enable": False,
        "entry_pricing": {
            "price_side": "other",
            "use_order_book": True,
            "order_book_top": 1,
            "price_last_balance": 0.0,
            "check_depth_of_market": {"enabled": False, "bids_to_ask_delta": 1},
        },
        "exit_pricing": {
            "price_side": "other",
            "use_order_book": True,
            "order_book_top": 1,
        },
    }


def apply_btc_regime_pulse_supertrend_indicators(
    dataframe: pd.DataFrame,
    params: dict[str, Any],
) -> pd.DataFrame:
    frame = dataframe.sort_values("date").copy()
    frame["hl2"] = (frame["high"] + frame["low"]) / 2.0
    frame["atr"] = ta.ATR(frame, timeperiod=int(params["atr_length"]))
    frame["atr_safe"] = frame["atr"].fillna(0.001).clip(lower=0.001)
    frame["atr_ma"] = frame["atr"].rolling(int(params["regime_lookback"])).mean()
    frame["atr_ratio"] = np.where(frame["atr_ma"] > 0, frame["atr"] / frame["atr_ma"], 1.0)
    frame["adx"] = ta.ADX(frame, timeperiod=int(params["adx_length"]))
    frame["regime"] = np.select(
        [
            frame["atr_ratio"] > 1.4,
            (frame["adx"] < float(params["adx_threshold"])) & (frame["atr_ratio"] < 0.9),
        ],
        [2, 0],
        default=1,
    ).astype(int)
    base_multiplier = float(params["base_multiplier"])
    frame["adapt_mult"] = np.where(
        frame["regime"] == 2,
        base_multiplier * (1.0 + (frame["atr_ratio"] - 1.0).clip(lower=0.0) * 0.4),
        np.where(frame["regime"] == 0, base_multiplier * 0.85, base_multiplier),
    )
    frame["adapt_mult"] = frame["adapt_mult"].clip(lower=base_multiplier * 0.5, upper=base_multiplier * 2.0)
    frame["upper_base"] = frame["hl2"] + frame["adapt_mult"] * frame["atr"]
    frame["lower_base"] = frame["hl2"] - frame["adapt_mult"] * frame["atr"]

    st_band: list[float] = []
    st_dir: list[int] = []
    prev_dir = 1
    prev_band = np.nan
    for row in frame.itertuples():
        upper_base = float(row.upper_base) if pd.notna(row.upper_base) else float(row.hl2)
        lower_base = float(row.lower_base) if pd.notna(row.lower_base) else float(row.hl2)
        band_seed = prev_band if pd.notna(prev_band) else (lower_base if prev_dir == 1 else upper_base)
        next_dir = prev_dir
        if prev_dir == 1:
            next_band = max(lower_base, band_seed)
            if float(row.close) < next_band:
                next_dir = -1
                next_band = upper_base
        else:
            next_band = min(upper_base, band_seed)
            if float(row.close) > next_band:
                next_dir = 1
                next_band = lower_base
        st_band.append(float(next_band))
        st_dir.append(int(next_dir))
        prev_band = next_band
        prev_dir = next_dir

    frame["st_band"] = st_band
    frame["st_dir"] = st_dir
    frame["trend_flip_up"] = (frame["st_dir"] == 1) & (frame["st_dir"].shift(1) == -1)
    frame["trend_flip_down"] = (frame["st_dir"] == -1) & (frame["st_dir"].shift(1) == 1)
    frame["trend_ema"] = ta.EMA(frame, timeperiod=int(params["trend_ema_length"]))
    frame["trend_up"] = frame["close"] > frame["trend_ema"]
    frame["trend_down"] = frame["close"] < frame["trend_ema"]
    frame["volume_ma"] = ta.SMA(frame["volume"], timeperiod=int(params["volume_ma_length"]))
    frame["volume_ratio"] = np.where(frame["volume_ma"] > 0, frame["volume"] / frame["volume_ma"], 1.0)
    frame["prev_band_distance"] = (frame["close"].shift(1) - frame["st_band"].shift(1)).abs() / frame["atr_safe"]
    frame["ema_distance_atr"] = (frame["close"] - frame["trend_ema"]).abs() / frame["atr_safe"]
    frame["long_disp_atr"] = (frame["close"] - frame["st_band"]) / frame["atr_safe"]
    frame["short_disp_atr"] = (frame["st_band"] - frame["close"]) / frame["atr_safe"]
    return frame


def apply_btc_regime_pulse_supertrend_entries(
    dataframe: pd.DataFrame,
    params: dict[str, Any],
) -> pd.DataFrame:
    frame = dataframe.copy()
    volume_score = np.select(
        [
            frame["volume_ratio"] >= 2.5,
            frame["volume_ratio"] >= 1.5,
            frame["volume_ratio"] >= 1.0,
        ],
        [20, 14, 8],
        default=3,
    )
    regime_score = np.select([frame["regime"] == 1, frame["regime"] == 2], [15, 8], default=3)
    band_distance_score = np.select(
        [
            frame["prev_band_distance"] >= 2.0,
            frame["prev_band_distance"] >= 1.0,
            frame["prev_band_distance"] >= 0.5,
        ],
        [20, 14, 8],
        default=3,
    )
    long_disp_score = np.select(
        [
            frame["long_disp_atr"] >= 1.5,
            frame["long_disp_atr"] >= 0.8,
            frame["long_disp_atr"] >= 0.3,
            frame["long_disp_atr"] > 0,
        ],
        [25, 18, 12, 5],
        default=0,
    )
    short_disp_score = np.select(
        [
            frame["short_disp_atr"] >= 1.5,
            frame["short_disp_atr"] >= 0.8,
            frame["short_disp_atr"] >= 0.3,
            frame["short_disp_atr"] > 0,
        ],
        [25, 18, 12, 5],
        default=0,
    )
    long_align_score = np.select(
        [
            frame["trend_up"] & (frame["ema_distance_atr"] > 0.5),
            frame["trend_up"],
            frame["ema_distance_atr"] < 0.3,
        ],
        [20, 14, 8],
        default=2,
    )
    short_align_score = np.select(
        [
            frame["trend_down"] & (frame["ema_distance_atr"] > 0.5),
            frame["trend_down"],
            frame["ema_distance_atr"] < 0.3,
        ],
        [20, 14, 8],
        default=2,
    )
    frame["long_score"] = np.rint(volume_score + long_disp_score + long_align_score + regime_score + band_distance_score).clip(0, 100)
    frame["short_score"] = np.rint(volume_score + short_disp_score + short_align_score + regime_score + band_distance_score).clip(0, 100)
    frame["long_candidate"] = (
        frame["trend_flip_up"]
        & (frame["long_score"] >= int(params["min_signal_score"]))
        & frame["trend_up"]
        & (frame["regime"] != 0)
        & (frame["volume"] > frame["volume_ma"].fillna(np.inf))
    )
    frame["short_candidate"] = (
        frame["trend_flip_down"]
        & (frame["short_score"] >= int(params["min_signal_score"]))
        & frame["trend_down"]
        & (frame["regime"] != 0)
        & (frame["volume"] > frame["volume_ma"].fillna(np.inf))
    )

    enter_long = np.zeros(len(frame), dtype=int)
    enter_short = np.zeros(len(frame), dtype=int)
    last_entry_index = -9999
    cooldown_bars = int(params["cooldown_bars"])
    for index, row in enumerate(frame.itertuples()):
        if index - last_entry_index <= cooldown_bars:
            continue
        if bool(row.long_candidate):
            enter_long[index] = 1
            last_entry_index = index
            continue
        if bool(row.short_candidate):
            enter_short[index] = 1
            last_entry_index = index

    frame["signal_enter_long"] = enter_long
    frame["signal_enter_short"] = enter_short
    frame["signal_long_tag"] = [
        f"long_s{int(score)}" if flag else None
        for flag, score in zip(enter_long, frame["long_score"], strict=False)
    ]
    frame["signal_short_tag"] = [
        f"short_s{int(score)}" if flag else None
        for flag, score in zip(enter_short, frame["short_score"], strict=False)
    ]
    return frame


def apply_btc_regime_pulse_supertrend_signal_frame(
    dataframe: pd.DataFrame,
    params: dict[str, Any],
) -> pd.DataFrame:
    frame = apply_btc_regime_pulse_supertrend_indicators(dataframe, params)
    frame = apply_btc_regime_pulse_supertrend_entries(frame, params)
    frame["active_regime"] = np.select(
        [frame["regime"] == 0, frame["regime"] == 2],
        ["range", "volatile_trend"],
        default="trend",
    )
    frame["long_entry_signal"] = frame["signal_enter_long"].astype(bool)
    frame["long_exit_signal"] = pd.Series(False, index=frame.index, dtype=bool)
    frame["short_entry_signal"] = frame["signal_enter_short"].astype(bool)
    frame["short_exit_signal"] = pd.Series(False, index=frame.index, dtype=bool)
    return frame


def _build_btc_regime_pulse_supertrend(strategy_class_name: str, timeframe: str) -> str:
    runtime_block = render_freqtrade_strategy_runtime(
        resolve_freqtrade_strategy_runtime(
            can_short=True,
            timeframe=timeframe,
            startup_candle_count=WARMUP_BARS,
            risk={
                "stoploss": -0.99,
                "trailing": {"enabled": False, "positive": 0.0, "offset": 0.0, "only_offset_reached": True},
            },
            roi_targets={"0": 99.0},
            order_types={"entry": "market", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False},
            has_exit_signals=False,
            has_custom_exit=True,
            position_adjustment_enable=False,
        )
    )
    helper_source = _render_core_source()
    params = repr(BTC_REGIME_PULSE_SUPERTREND_PARAMS)
    return f"""from typing import Any

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy

BTC_REGIME_PULSE_SUPERTREND_PARAMS: dict[str, Any] = {params}

{helper_source}


class {strategy_class_name}(IStrategy):
{runtime_block}

    atr_length = BTC_REGIME_PULSE_SUPERTREND_PARAMS["atr_length"]
    base_multiplier = BTC_REGIME_PULSE_SUPERTREND_PARAMS["base_multiplier"]
    regime_lookback = BTC_REGIME_PULSE_SUPERTREND_PARAMS["regime_lookback"]
    adx_length = BTC_REGIME_PULSE_SUPERTREND_PARAMS["adx_length"]
    adx_threshold = BTC_REGIME_PULSE_SUPERTREND_PARAMS["adx_threshold"]
    trend_ema_length = BTC_REGIME_PULSE_SUPERTREND_PARAMS["trend_ema_length"]
    volume_ma_length = BTC_REGIME_PULSE_SUPERTREND_PARAMS["volume_ma_length"]
    min_signal_score = BTC_REGIME_PULSE_SUPERTREND_PARAMS["min_signal_score"]
    cooldown_bars = BTC_REGIME_PULSE_SUPERTREND_PARAMS["cooldown_bars"]
    stoploss_atr_multiplier = BTC_REGIME_PULSE_SUPERTREND_PARAMS["stoploss_atr_multiplier"]
    takeprofit_rr = BTC_REGIME_PULSE_SUPERTREND_PARAMS["takeprofit_rr"]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return apply_btc_regime_pulse_supertrend_entries(
            apply_btc_regime_pulse_supertrend_indicators(dataframe, BTC_REGIME_PULSE_SUPERTREND_PARAMS),
            BTC_REGIME_PULSE_SUPERTREND_PARAMS,
        )

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = dataframe["signal_enter_long"].fillna(0).astype(int)
        dataframe["enter_short"] = dataframe["signal_enter_short"].fillna(0).astype(int)
        dataframe["enter_tag"] = dataframe["signal_long_tag"]
        dataframe["enter_short_tag"] = dataframe["signal_short_tag"]
        dataframe.loc[dataframe["enter_short"] > 0, "enter_tag"] = dataframe.loc[dataframe["enter_short"] > 0, "signal_short_tag"]
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        dataframe["exit_tag"] = None
        dataframe["exit_short_tag"] = None
        return dataframe

    def _resolve_exit_plan(self, pair, trade, dataframe: DataFrame | None = None):
        cached_plan = trade.get_custom_data("pulse_exit_plan")
        if cached_plan:
            return cached_plan
        if dataframe is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None
        entry_frame = dataframe.loc[dataframe["date"] <= pd.Timestamp(trade.open_date_utc)]
        if entry_frame.empty:
            return None
        entry_candle = entry_frame.iloc[-1]
        atr_raw = entry_candle.get("atr")
        atr_value = float(atr_raw) if pd.notna(atr_raw) else 0.0
        entry_price = float(trade.open_rate)
        stop_distance = max(atr_value * self.stoploss_atr_multiplier, entry_price * 0.0005)
        target_distance = stop_distance * self.takeprofit_rr
        if trade.is_short:
            resolved_plan = {{"stop": entry_price + stop_distance, "target": entry_price - target_distance}}
        else:
            resolved_plan = {{"stop": entry_price - stop_distance, "target": entry_price + target_distance}}
        if getattr(trade, "id", None) is not None:
            trade.set_custom_data("pulse_exit_plan", resolved_plan)
        return resolved_plan
{render_threshold_custom_exit(
    plan_var_name="exit_plan",
    resolve_plan_expression="self._resolve_exit_plan(pair, trade, dataframe)",
    stop_reason="atr_stop",
    target_reason="rr_target",
)}"""


def _render_core_source() -> str:
    return "\n\n".join(
        textwrap.dedent(inspect.getsource(function)).strip()
        for function in (
            apply_btc_regime_pulse_supertrend_indicators,
            apply_btc_regime_pulse_supertrend_entries,
        )
    )


def _base_signal_frame(candles: list[list[float]]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["timestamp", "date", "open", "high", "low", "close", "volume"])
    frame = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    return frame.sort_values("date").reset_index(drop=True)


def _build_signal_frame_from_candles(candles: list[list[float]], _timeframe: str) -> pd.DataFrame:
    frame = _base_signal_frame(candles)
    if frame.empty:
        return frame
    return apply_btc_regime_pulse_supertrend_signal_frame(frame, BTC_REGIME_PULSE_SUPERTREND_PARAMS)
