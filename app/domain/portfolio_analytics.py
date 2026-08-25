from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
import statistics
from typing import Any


def analyze_portfolio(
    *,
    portfolio_id: str,
    transactions: list[dict[str, Any]],
    ledger_summary: dict[str, Any],
    price_history: dict[str, dict[str, float]],
    benchmark_symbol: str,
    benchmark_history: dict[str, float],
    period_days: int,
    custom_shocks: dict[str, float],
    start_date: str,
    end_date: str,
    issues: list[str],
) -> dict[str, Any]:
    positions = [item for item in ledger_summary.get("positions", []) if item.get("marketValue", 0) > 0]
    total_equity = float(ledger_summary.get("totalEquity") or 0)
    total_market_value = sum(float(item["marketValue"]) for item in positions)
    weights = {
        item["symbol"]: float(item["marketValue"]) / total_market_value for item in positions if total_market_value > 0
    }
    symbols = sorted(weights)
    asset_returns = {symbol: _return_series(price_history.get(symbol, {})) for symbol in symbols}
    correlation = _correlation_matrix(symbols, asset_returns)
    covariance = _covariance_matrix(symbols, asset_returns)
    portfolio_volatility, contributions = _portfolio_risk(symbols, weights, covariance)
    performance = _build_performance(transactions, price_history, start_date, end_date)
    time_weighted = _time_weighted_return(performance)
    max_drawdown = max((point["drawdownPct"] for point in performance), default=None)
    benchmark_return = _period_return(benchmark_history)
    hhi = sum(weight * weight for weight in weights.values())
    top_weight = max(weights.values(), default=0) * 100
    daily_portfolio_returns = _static_portfolio_returns(symbols, weights, asset_returns)
    worst_shocks = _worst_observed_shocks(symbols, weights, asset_returns)

    assets = []
    for symbol in symbols:
        returns = list(asset_returns.get(symbol, {}).values())
        period_return = _period_return(price_history.get(symbol, {}))
        annual_vol = statistics.stdev(returns) * math.sqrt(365) * 100 if len(returns) >= 2 else None
        assets.append(
            {
                "symbol": symbol,
                "weightPct": weights[symbol] * 100,
                "annualizedVolatilityPct": annual_vol,
                "riskContributionPct": contributions.get(symbol),
                "periodReturnPct": period_return,
                "returnContributionPct": period_return * weights[symbol] if period_return is not None else None,
            }
        )

    scenario_specs = [
        ("observed_worst_day", "历史最差共同交易日", worst_shocks),
        ("broad_risk_off", "广泛风险资产下跌 25%", {symbol: -25.0 for symbol in symbols}),
    ]
    if custom_shocks:
        scenario_specs.append(("custom", "自定义冲击", custom_shocks))
    scenarios = [
        _scenario(identifier, name, shocks, positions, total_equity)
        for identifier, name, shocks in scenario_specs
        if shocks
    ]
    var95 = (
        1.645 * statistics.stdev(daily_portfolio_returns) * total_equity if len(daily_portfolio_returns) >= 2 else None
    )
    excess = time_weighted - benchmark_return if time_weighted is not None and benchmark_return is not None else None
    return {
        "portfolioId": portfolio_id,
        "startDate": start_date,
        "endDate": end_date,
        "periodDays": period_days,
        "totalEquity": total_equity,
        "timeWeightedReturnPct": time_weighted,
        "moneyWeightedReturnPct": ledger_summary.get("moneyWeightedReturnPct"),
        "benchmarkSymbol": benchmark_symbol,
        "benchmarkReturnPct": benchmark_return,
        "excessReturnPct": excess,
        "annualizedVolatilityPct": portfolio_volatility,
        "valueAtRisk95": var95,
        "maxDrawdownPct": max_drawdown,
        "concentrationHhi": hhi,
        "effectivePositionCount": 1 / hhi if hhi > 0 else None,
        "topPositionWeightPct": top_weight,
        "symbols": symbols,
        "correlation": [{"symbol": symbol, "values": correlation[index]} for index, symbol in enumerate(symbols)],
        "assets": assets,
        "performance": performance,
        "scenarios": scenarios,
        "issues": issues,
    }


def _build_performance(
    transactions: list[dict[str, Any]],
    histories: dict[str, dict[str, float]],
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    all_dates = sorted(
        value for value in {day for history in histories.values() for day in history} if start_date <= value <= end_date
    )
    if not all_dates:
        return []
    ordered = sorted(transactions, key=lambda item: (item["occurredAt"], item["id"]))
    cash = 0.0
    units: dict[str, float] = defaultdict(float)
    prices: dict[str, float] = {}
    cursor = 0
    previous_equity = None
    cumulative = 1.0
    peak = 0.0
    points = []
    for day in all_dates:
        flow = 0.0
        day_end = datetime.fromisoformat(f"{day}T23:59:59")
        while cursor < len(ordered):
            item = ordered[cursor]
            occurred = item["occurredAt"]
            occurred = (
                occurred
                if isinstance(occurred, datetime)
                else datetime.fromisoformat(str(occurred).replace("Z", "+00:00")).replace(tzinfo=None)
            )
            if occurred > day_end:
                break
            kind = item["transactionType"]
            amount = float(item.get("cashAmount") or 0)
            quantity = float(item.get("quantity") or 0)
            price = float(item.get("unitPrice") or 0)
            fee = float(item.get("fee") or 0)
            symbol = str(item.get("symbol") or "").upper()
            if kind == "deposit":
                cash += amount
                flow += amount
            elif kind == "withdrawal":
                cash -= amount
                flow -= amount
            elif kind == "fee":
                cash -= amount
            elif kind == "buy":
                units[symbol] += quantity
                cash -= quantity * price + fee
            elif kind == "sell":
                units[symbol] -= quantity
                cash += quantity * price - fee
            elif kind == "transfer_in":
                units[symbol] += quantity
            elif kind == "transfer_out":
                units[symbol] -= quantity
            cursor += 1
        for symbol, history in histories.items():
            if day in history:
                prices[symbol] = history[day]
        equity = cash + sum(quantity * prices.get(symbol, 0) for symbol, quantity in units.items())
        daily_return = None
        if previous_equity is not None and abs(previous_equity) > 1e-12:
            daily_return = (equity - flow) / previous_equity - 1
            cumulative *= 1 + daily_return
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak * 100 if peak > 0 else 0.0
        points.append(
            {
                "date": day,
                "equity": equity,
                "externalCashFlow": flow,
                "dailyReturnPct": daily_return * 100 if daily_return is not None else None,
                "drawdownPct": drawdown,
                "_cumulative": cumulative,
            }
        )
        previous_equity = equity
    for point in points:
        point.pop("_cumulative", None)
    return points


def _time_weighted_return(points: list[dict[str, Any]]) -> float | None:
    returns = [point["dailyReturnPct"] / 100 for point in points if point["dailyReturnPct"] is not None]
    if not returns:
        return None
    result = 1.0
    for value in returns:
        result *= 1 + value
    return (result - 1) * 100


def _return_series(history: dict[str, float]) -> dict[str, float]:
    result = {}
    previous = None
    for day, price in sorted(history.items()):
        if previous and previous > 0:
            result[day] = price / previous - 1
        previous = price
    return result


def _period_return(history: dict[str, float]) -> float | None:
    values = [value for _, value in sorted(history.items()) if value > 0]
    return (values[-1] / values[0] - 1) * 100 if len(values) >= 2 else None


def _pair_correlation(left: dict[str, float], right: dict[str, float]) -> float | None:
    dates = sorted(set(left) & set(right))
    if len(dates) < 3:
        return None
    left_values, right_values = [left[d] for d in dates], [right[d] for d in dates]
    left_mean, right_mean = statistics.mean(left_values), statistics.mean(right_values)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_values, right_values))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left_values) * sum((b - right_mean) ** 2 for b in right_values)
    )
    return max(-1.0, min(1.0, numerator / denominator)) if denominator > 0 else None


def _correlation_matrix(symbols, returns):
    return [
        [1.0 if left == right else _pair_correlation(returns[left], returns[right]) for right in symbols]
        for left in symbols
    ]


def _covariance_matrix(symbols, returns):
    matrix = []
    for left in symbols:
        row = []
        for right in symbols:
            dates = sorted(set(returns[left]) & set(returns[right]))
            if len(dates) < 2:
                row.append(None)
                continue
            a, b = [returns[left][d] for d in dates], [returns[right][d] for d in dates]
            am, bm = statistics.mean(a), statistics.mean(b)
            row.append(sum((x - am) * (y - bm) for x, y in zip(a, b)) / (len(dates) - 1))
        matrix.append(row)
    return matrix


def _portfolio_risk(symbols, weights, covariance):
    if not symbols or any(value is None for row in covariance for value in row):
        return None, {}
    w = [weights[symbol] for symbol in symbols]
    marginal = [sum(covariance[i][j] * w[j] for j in range(len(w))) for i in range(len(w))]
    variance = sum(w[i] * marginal[i] for i in range(len(w)))
    if variance <= 0:
        return None, {}
    contributions = {symbols[i]: w[i] * marginal[i] / variance * 100 for i in range(len(w))}
    return math.sqrt(variance) * math.sqrt(365) * 100, contributions


def _static_portfolio_returns(symbols, weights, returns):
    dates = sorted(set.intersection(*(set(returns[symbol]) for symbol in symbols))) if symbols else []
    return [sum(weights[symbol] * returns[symbol][day] for symbol in symbols) for day in dates]


def _worst_observed_shocks(symbols, weights, returns):
    dates = sorted(set.intersection(*(set(returns[symbol]) for symbol in symbols))) if symbols else []
    if not dates:
        return {}
    worst = min(dates, key=lambda day: sum(weights[symbol] * returns[symbol][day] for symbol in symbols))
    return {symbol: returns[symbol][worst] * 100 for symbol in symbols}


def _scenario(identifier, name, shocks, positions, total_equity):
    values = {item["symbol"]: float(item["marketValue"]) for item in positions}
    pnl = sum(values.get(symbol, 0) * float(shock) / 100 for symbol, shock in shocks.items())
    return {
        "id": identifier,
        "name": name,
        "shocks": shocks,
        "projectedPnl": pnl,
        "projectedReturnPct": pnl / total_equity * 100 if total_equity else None,
        "projectedEquity": total_equity + pnl,
    }
