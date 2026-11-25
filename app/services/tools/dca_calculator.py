from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from utils.time import get_timezone


def prepare_dca_dataset(
    klines: list[list[Any]],
    *,
    timezone: str,
    start_dt_local: datetime,
    target_hour: int | None,
    strategy: str | None = None,
) -> pd.DataFrame:
    all_df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume"])
    all_df["datetime"] = pd.to_datetime(all_df["timestamp"], unit="ms", utc=True).astype("datetime64[ns, UTC]")
    tz_obj = get_timezone(timezone)
    all_df["local_dt"] = all_df["datetime"].dt.tz_convert(tz_obj)

    fields = {"ema_deviation": "ema20", "rsi_dynamic": "rsi", "ahr999": "ahr999"}
    requested = list(fields.values()) if strategy is None else [fields[strategy]] if strategy in fields else []
    if requested or target_hour is None:
        daily_df = all_df.set_index("datetime").resample("D").agg({"close": "last"}).dropna()
        if "ema20" in requested:
            daily_df["ema20"] = daily_df["close"].ewm(span=20, adjust=False).mean()
        if "rsi" in requested:
            delta = daily_df["close"].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            daily_df["rsi"] = 100 - (100 / (1 + (gain / loss).fillna(0)))
        if "ahr999" in requested:
            daily_df["ma200"] = daily_df["close"].rolling(window=settings.DCA_MA_PERIOD).mean()
            genesis_date = datetime.strptime(settings.BTC_GENESIS_DATE, "%Y-%m-%d")
            daily_df["age_days"] = (daily_df.index.tz_localize(None) - genesis_date).days
            daily_df = daily_df[daily_df["age_days"] > 0]
            log_age = np.log10(daily_df["age_days"])
            daily_df["exp_price"] = 10 ** (settings.AHR999_COEFF_A * log_age - settings.AHR999_COEFF_B)
            daily_df["ahr999"] = (daily_df["close"] / daily_df["ma200"]) * (daily_df["close"] / daily_df["exp_price"])
        daily_df["date_str"] = daily_df.index.strftime("%Y-%m-%d")
        if target_hour is None:
            daily_df["datetime"] = daily_df.index
            return daily_df[daily_df.index.tz_localize(None) >= start_dt_local].copy()

    dataset = all_df
    if requested:
        # UTC daily observations become available at the next UTC midnight.
        indicators = daily_df[requested].copy()
        indicators["available_at"] = (indicators.index + pd.Timedelta(days=1)).astype("datetime64[ns, UTC]")
        dataset = pd.merge_asof(all_df.sort_values("datetime"), indicators.reset_index(drop=True),
                                left_on="datetime", right_on="available_at", direction="backward")
    dataset["close"] = dataset["open"]
    dataset["date_str"] = dataset["datetime"].dt.strftime("%Y-%m-%d")
    filtered = dataset[dataset["local_dt"] >= start_dt_local.replace(tzinfo=tz_obj)].copy()
    return filtered[filtered["local_dt"].dt.hour == target_hour].copy()


def simulate_dca_schedule(
    target_klines: pd.DataFrame,
    *,
    daily_investment: float,
    strategy: str,
    strategy_params: dict[str, Any] | None,
    sentiment_map: dict[str, int],
) -> tuple[list[dict[str, Any]], float, float]:
    total_invested = 0.0
    total_coins = 0.0
    history: list[dict[str, Any]] = []
    params = strategy_params or {}
    multiplier_strength = params.get("multiplier", settings.DCA_DEFAULT_MULTIPLIER)
    fee_rate = params.get("fee_rate", 0.001)

    for day_count, (_, row) in enumerate(target_klines.iterrows()):
        price = row["close"]
        if price <= 0:
            continue

        current_investment = daily_investment
        multiplier = 1.0

        if strategy == "ema_deviation":
            ema_val = row["ema20"]
            if pd.notna(ema_val) and ema_val > 0:
                multiplier = 1 + (multiplier_strength * ((ema_val - price) / ema_val))
        elif strategy == "rsi_dynamic":
            rsi = row.get("rsi")
            if pd.notna(rsi):
                multiplier = 1 + multiplier_strength * (50 - rsi) / 50
        elif strategy == "ahr999":
            ahr = row.get("ahr999")
            if pd.notna(ahr) and ahr > 0:
                try:
                    multiplier = 1 / (ahr ** (multiplier_strength * 0.3))
                except (ValueError, ZeroDivisionError, OverflowError):
                    multiplier = 1.0
                multiplier = max(settings.DCA_MULTIPLIER_MIN, min(multiplier, settings.DCA_MULTIPLIER_MAX))
        elif strategy == "fear_greed":
            dt_val = row.get("datetime")
            # Historical daily sentiment has no intraday publication timestamp.
            # Only the preceding UTC day's observation is safe for scheduled decisions.
            date_str = (dt_val - pd.Timedelta(days=1)).strftime("%Y-%m-%d") if pd.notna(dt_val) else ""
            sentiment_value = sentiment_map.get(date_str)
            if sentiment_value is not None:
                multiplier = 1 + multiplier_strength * (50 - sentiment_value) / 50

        if strategy == "value_averaging":
            target_total_value = (day_count + 1) * daily_investment
            current_holdings_value = total_coins * price
            current_investment = target_total_value - current_holdings_value
            if current_investment < 0:
                current_investment = -min(abs(current_investment), current_holdings_value)
            elif current_investment > 0:
                current_investment = min(current_investment, daily_investment * settings.DCA_VA_MAX_MULTIPLE)
        else:
            if strategy != "standard":
                current_investment = daily_investment * multiplier
            current_investment = max(0, min(current_investment, daily_investment * settings.DCA_STANDARD_MAX_MULTIPLE))

        if current_investment >= 0:
            # Buys spend the cash budget, with the fee reducing acquired assets.
            coins_change = current_investment * (1 - fee_rate) / price
            cash_change = current_investment
        else:
            # Sells remove the gross asset value; only net proceeds reduce cash
            # invested. Applying the buy formula here would retain extra coins.
            coins_change = current_investment / price
            cash_change = current_investment * (1 - fee_rate)
        total_invested += cash_change
        total_coins += coins_change
        if total_coins < settings.DCA_COIN_PRECISION:
            total_coins = 0.0

        current_value = total_coins * price
        roi_percent = ((current_value - total_invested) / total_invested) * 100 if total_invested > 0 else 0.0
        avg_cost = total_invested / total_coins if total_coins > 0 else 0
        history.append(
            {
                "date": row["datetime"].strftime("%Y-%m-%d")
                if pd.notna(row.get("datetime"))
                else row.get("date_str", ""),
                "price": price,
                "invested": round(total_invested, 2),
                "value": round(current_value, 2),
                "coins": round(total_coins, 6),
                "roi": round(roi_percent, 2),
                "avg_cost": round(avg_cost, 2),
            }
        )

    return history, total_invested, total_coins
