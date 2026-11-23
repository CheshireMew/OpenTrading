from __future__ import annotations

from math import sqrt
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.domain.market.history.indicators import latest_indicator_summary
from app.domain.market.history.models import PriceSnapshot


def calculate_analytics(
    snapshot: PriceSnapshot,
    requested_basis: Literal["raw", "adjusted", "both"],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    available = ["raw"]
    if any(bar.adjusted_close != bar.close for bar in snapshot.bars) or snapshot.instrument.asset_class in {"stock", "etf"}:
        available.append("adjusted")
    primary = "adjusted" if snapshot.instrument.asset_class in {"stock", "etf"} else "raw"
    if requested_basis in {"raw", "adjusted"}:
        primary = requested_basis
    price_basis = {
        "requested": requested_basis,
        "primary": primary,
        "available": available,
        "contract": {
            "version": "price-adjustment.v1",
            "raw_ohlc": True,
            "adjusted_close": "provider-supplied when available",
            "adjusted_ohlc": False,
            "corporate_actions": "dividend and split fields are preserved; no client-side qfq/hfq reconstruction",
        },
    }
    bases: tuple[Literal["raw", "adjusted"], ...] = (
        ("raw", "adjusted") if requested_basis == "both" else (requested_basis,)
    )
    calculated = {basis: _calculate(snapshot, basis) for basis in bases}
    if requested_basis == "both":
        return (
            price_basis,
            {basis: calculated[basis][0] for basis in bases},
            {basis: calculated[basis][1] for basis in bases},
        )
    statistics, indicators = calculated[requested_basis]
    return price_basis, statistics, indicators


def _calculate(
    snapshot: PriceSnapshot,
    basis: Literal["raw", "adjusted"],
) -> tuple[dict[str, Any], dict[str, Any]]:
    values = [bar.adjusted_close if basis == "adjusted" else bar.close for bar in snapshot.bars]
    index = pd.DatetimeIndex([bar.observed_at for bar in snapshot.bars])
    prices = pd.Series(values, index=index, dtype="float64")
    volumes = pd.Series([bar.volume for bar in snapshot.bars], index=index, dtype="float64")
    reasons: dict[str, str] = {}
    if prices.empty:
        return _empty_statistics(), latest_indicator_summary(snapshot, basis)

    returns = prices.pct_change(fill_method=None).dropna()
    elapsed_days = (prices.index[-1].date() - prices.index[0].date()).days
    total_return = _finite(prices.iloc[-1] / prices.iloc[0] - 1) if len(prices) >= 2 else None
    cagr = None
    if len(prices) >= 2 and elapsed_days > 0:
        cagr = _finite((prices.iloc[-1] / prices.iloc[0]) ** (365.2425 / elapsed_days) - 1)
    else:
        reasons["cagr"] = "at least two distinct dates are required"
    annualization = 365 if snapshot.instrument.asset_class == "crypto" else 252
    volatility = _finite(returns.std(ddof=1) * sqrt(annualization)) if len(returns) >= 2 else None
    if volatility is None:
        reasons["annualized_volatility"] = "at least three price records are required"

    drawdowns = prices / prices.cummax() - 1
    trough_time = drawdowns.idxmin()
    peak_window = prices.loc[:trough_time]
    peak_time = peak_window.idxmax()
    period_high_time = prices.idxmax()
    period_low_time = prices.idxmin()
    span = prices.max() - prices.min()
    position = _finite((prices.iloc[-1] - prices.min()) / span) if span else None
    if position is None:
        reasons["range_position"] = "period high and low are equal"

    non_null_volume = volumes.dropna()
    average_volume_20 = _finite(non_null_volume.tail(20).mean()) if len(non_null_volume) >= 20 else None
    latest_volume = _finite(non_null_volume.iloc[-1]) if len(non_null_volume) else None
    volume_ratio = None
    if latest_volume is not None and average_volume_20 is not None and average_volume_20 != 0:
        volume_ratio = _finite(latest_volume / average_volume_20)
    if average_volume_20 is None:
        reasons["average_volume_20"] = "20 volume observations are required"

    statistics = {
        "first_price": _finite(prices.iloc[0]),
        "latest_price": _finite(prices.iloc[-1]),
        "period_return": total_return,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "annualization_days": annualization,
        "max_drawdown": _finite(drawdowns.min()),
        "max_drawdown_peak_date": peak_time.date().isoformat(),
        "max_drawdown_trough_date": trough_time.date().isoformat(),
        "current_drawdown": _finite(drawdowns.iloc[-1]),
        "period_high": _finite(prices.max()),
        "period_high_date": period_high_time.date().isoformat(),
        "period_low": _finite(prices.min()),
        "period_low_date": period_low_time.date().isoformat(),
        "range_position": position,
        "average_volume_20": average_volume_20,
        "latest_volume": latest_volume,
        "latest_volume_multiple": volume_ratio,
        "unavailable_reasons": reasons,
    }

    indicators = latest_indicator_summary(snapshot, basis)
    return statistics, indicators


def _empty_statistics() -> dict[str, Any]:
    keys = (
        "first_price", "latest_price", "period_return", "cagr", "annualized_volatility",
        "max_drawdown", "max_drawdown_peak_date", "max_drawdown_trough_date",
        "current_drawdown", "period_high", "period_high_date", "period_low",
        "period_low_date", "range_position", "average_volume_20", "latest_volume",
        "latest_volume_multiple",
    )
    return {**{key: None for key in keys}, "annualization_days": None, "unavailable_reasons": {"all": "no usable price records"}}


def _finite(value: Any) -> float | None:
    numeric = float(value)
    return numeric if np.isfinite(numeric) else None
