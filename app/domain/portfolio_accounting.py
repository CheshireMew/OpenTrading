from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
from typing import Any


ASSET_IN_TYPES = {"buy", "transfer_in"}
ASSET_OUT_TYPES = {"sell", "transfer_out"}


def calculate_money_weighted_return(
    transactions: list[dict[str, Any]],
    *,
    terminal_value: float,
    terminal_date: datetime | None = None,
) -> float | None:
    """Annualized XIRR over external cash flows and the current liquidation value."""
    dated_flows: list[tuple[datetime, float]] = []
    for item in transactions:
        amount = max(float(item.get("cash_amount") or 0), 0.0)
        occurred_at = item.get("occurred_at")
        if not isinstance(occurred_at, datetime) or amount <= 0:
            continue
        if item.get("transaction_type") == "deposit":
            dated_flows.append((occurred_at, -amount))
        elif item.get("transaction_type") == "withdrawal":
            dated_flows.append((occurred_at, amount))
    if terminal_value > 0:
        dated_flows.append((terminal_date or datetime.now(timezone.utc).replace(tzinfo=None), terminal_value))
    if (
        len(dated_flows) < 2
        or not any(value < 0 for _, value in dated_flows)
        or not any(value > 0 for _, value in dated_flows)
    ):
        return None
    dated_flows.sort(key=lambda item: item[0])
    start = dated_flows[0][0]

    def npv(rate: float) -> float:
        return sum(
            value / ((1 + rate) ** max((date - start).total_seconds() / 31_557_600, 0)) for date, value in dated_flows
        )

    low, high = -0.9999, 1.0
    low_value, high_value = npv(low), npv(high)
    while low_value * high_value > 0 and high < 1_000_000:
        high *= 10
        high_value = npv(high)
    if not math.isfinite(low_value) or not math.isfinite(high_value) or low_value * high_value > 0:
        return None
    for _ in range(160):
        midpoint = (low + high) / 2
        value = npv(midpoint)
        if abs(value) < 1e-8:
            return midpoint * 100
        if low_value * value <= 0:
            high = midpoint
        else:
            low, low_value = midpoint, value
    return (low + high) / 2 * 100


def calculate_portfolio_ledger(
    transactions: list[dict[str, Any]],
    *,
    market_prices: dict[str, float],
) -> dict[str, Any]:
    positions: dict[str, dict[str, float]] = defaultdict(
        lambda: {"units": 0.0, "cost_basis": 0.0, "realized_pnl": 0.0, "fees": 0.0}
    )
    cash_balance = 0.0
    contributions = 0.0
    withdrawals = 0.0
    total_fees = 0.0
    issues: list[str] = []

    for transaction in sorted(transactions, key=lambda item: (item["occurred_at"], item["id"])):
        transaction_type = transaction["transaction_type"]
        symbol = str(transaction.get("symbol") or "").upper()
        quantity = max(float(transaction.get("quantity") or 0), 0.0)
        unit_price = max(float(transaction.get("unit_price") or 0), 0.0)
        cash_amount = max(float(transaction.get("cash_amount") or 0), 0.0)
        fee = max(float(transaction.get("fee") or 0), 0.0)
        total_fees += fee

        if transaction_type == "deposit":
            contributions += cash_amount
            cash_balance += cash_amount
            continue
        if transaction_type == "withdrawal":
            withdrawals += cash_amount
            cash_balance -= cash_amount
            continue
        if transaction_type == "fee":
            total_fees += cash_amount
            cash_balance -= cash_amount
            continue
        if not symbol:
            issues.append(f"流水 {transaction['id']} 缺少标的")
            continue

        position = positions[symbol]
        position["fees"] += fee
        if transaction_type in ASSET_IN_TYPES:
            acquired_cost = quantity * unit_price + fee
            position["units"] += quantity
            position["cost_basis"] += acquired_cost
            if transaction_type == "buy":
                cash_balance -= quantity * unit_price + fee
            continue

        if transaction_type in ASSET_OUT_TYPES:
            units_before = position["units"]
            if quantity > units_before + 1e-12:
                issues.append(f"{symbol} 在 {transaction['occurred_at']} 的转出数量超过当时持仓")
            disposed = min(quantity, max(units_before, 0.0))
            average_cost = position["cost_basis"] / units_before if units_before > 0 else 0.0
            removed_cost = average_cost * disposed
            position["units"] -= quantity
            position["cost_basis"] = max(position["cost_basis"] - removed_cost, 0.0)
            if transaction_type == "sell":
                proceeds = quantity * unit_price - fee
                cash_balance += proceeds
                position["realized_pnl"] += proceeds - removed_cost

    response_positions: list[dict[str, Any]] = []
    market_value = 0.0
    cost_basis = 0.0
    realized_pnl = 0.0
    unrealized_pnl = 0.0
    for symbol in sorted(positions):
        position = positions[symbol]
        units = position["units"]
        price = max(float(market_prices.get(symbol) or 0), 0.0)
        value = units * price
        unrealized = value - position["cost_basis"]
        market_value += value
        cost_basis += position["cost_basis"]
        realized_pnl += position["realized_pnl"]
        unrealized_pnl += unrealized
        response_positions.append(
            {
                "symbol": symbol,
                "units": units,
                "averageCost": position["cost_basis"] / units if units > 0 else 0.0,
                "costBasis": position["cost_basis"],
                "marketPrice": price if price > 0 else None,
                "marketValue": value,
                "realizedPnl": position["realized_pnl"],
                "unrealizedPnl": unrealized,
                "fees": position["fees"],
            }
        )

    net_contributions = contributions - withdrawals
    total_equity = cash_balance + market_value
    total_pnl = total_equity - net_contributions
    simple_return = total_pnl / net_contributions * 100 if net_contributions > 0 else None
    return {
        "cashBalance": cash_balance,
        "contributions": contributions,
        "withdrawals": withdrawals,
        "netContributions": net_contributions,
        "totalFees": total_fees,
        "costBasis": cost_basis,
        "marketValue": market_value,
        "totalEquity": total_equity,
        "realizedPnl": realized_pnl,
        "unrealizedPnl": unrealized_pnl,
        "totalPnl": total_pnl,
        "simpleReturnPct": simple_return,
        "moneyWeightedReturnPct": calculate_money_weighted_return(
            transactions,
            terminal_value=total_equity,
        ),
        "timeWeightedReturnPct": None,
        "positions": response_positions,
        "issues": issues,
        "reliability": "complete" if not issues else "incomplete",
    }
