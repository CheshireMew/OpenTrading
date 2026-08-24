from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from app.contracts.backtest import BacktestEquityPointRecord, BacktestTradeRecord
from app.contracts.backtest_result import BacktestPairBreakdownResponse, BacktestReportResponse, BacktestReportSnapshotResponse
from utils.time_utils import to_utc_naive_datetime


class FreqtradeReportBuilder:
    SNAPSHOT_KEYS = (
        "profit_pct",
        "profit_abs",
        "final_balance",
        "max_drawdown_pct",
        "sharpe",
        "calmar",
        "profit_factor",
        "win_rate",
        "total_trades",
    )

    def report_snapshot(self, report: BacktestReportResponse | dict[str, Any] | None) -> BacktestReportSnapshotResponse | None:
        if not report:
            return None
        payload = report.model_dump() if isinstance(report, BacktestReportResponse) else report
        return BacktestReportSnapshotResponse.model_validate({key: payload.get(key) for key in self.SNAPSHOT_KEYS})

    def extract_metric(self, report: BacktestReportResponse | dict[str, Any], metric: str) -> float | None:
        payload = report.model_dump() if isinstance(report, BacktestReportResponse) else report
        value = payload.get(metric)
        if value is None:
            return None
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return None
        return numeric

    def build_equity_curve(
        self,
        *,
        trades: list[BacktestTradeRecord],
        initial_cash: float,
        start_date: datetime,
        end_date: datetime,
    ) -> list[BacktestEquityPointRecord]:
        start_date = to_utc_naive_datetime(start_date)
        end_date = to_utc_naive_datetime(end_date)
        if trades:
            first_event = min((trade.opened_at for trade in trades), default=start_date)
            start_date = min(start_date, first_event - timedelta(seconds=1))
        points = [BacktestEquityPointRecord(timestamp=start_date, equity=initial_cash, pnl_abs=0.0, drawdown_pct=0.0)]
        if not trades:
            return points
        running_equity = initial_cash
        peak_equity = initial_cash
        for trade in sorted(trades, key=lambda item: item.closed_at or item.opened_at):
            event_time = trade.closed_at or trade.opened_at
            running_equity += trade.profit_abs
            peak_equity = max(peak_equity, running_equity)
            drawdown_pct = ((peak_equity - running_equity) / peak_equity * 100.0) if peak_equity else 0.0
            points.append(
                BacktestEquityPointRecord(
                    timestamp=event_time,
                    equity=running_equity,
                    pnl_abs=running_equity - initial_cash,
                    drawdown_pct=drawdown_pct,
                )
            )
        if points[-1].timestamp < end_date:
            points.append(
                BacktestEquityPointRecord(
                    timestamp=end_date,
                    equity=running_equity,
                    pnl_abs=running_equity - initial_cash,
                    drawdown_pct=((peak_equity - running_equity) / peak_equity * 100.0) if peak_equity else 0.0,
                )
            )
        return sorted(points, key=lambda item: item.timestamp)

    def build_report(
        self,
        *,
        trades: list[BacktestTradeRecord],
        equity_curve: list[BacktestEquityPointRecord],
        initial_cash: float,
        start_date: datetime,
        end_date: datetime,
    ) -> BacktestReportResponse:
        profit_abs = sum(trade.profit_abs for trade in trades)
        final_balance = initial_cash + profit_abs
        wins = [trade for trade in trades if trade.profit_abs > 0]
        losses = [trade for trade in trades if trade.profit_abs < 0]
        draws = [trade for trade in trades if trade.profit_abs == 0]
        gross_profit = sum(trade.profit_abs for trade in wins)
        gross_loss_abs = abs(sum(trade.profit_abs for trade in losses))
        max_drawdown_pct = max((point.drawdown_pct for point in equity_curve), default=0.0)
        annualized = self._annualized_return_pct(initial_cash, final_balance, start_date, end_date)
        returns = self._equity_returns(equity_curve)
        return BacktestReportResponse(
            initial_cash=initial_cash,
            final_balance=final_balance,
            profit_abs=profit_abs,
            profit_pct=((final_balance / initial_cash - 1.0) * 100.0) if initial_cash else 0.0,
            annualized_return_pct=annualized,
            max_drawdown_pct=max_drawdown_pct,
            sharpe=self._sharpe_ratio(returns),
            sortino=self._sortino_ratio(returns),
            calmar=(annualized / max_drawdown_pct) if annualized is not None and max_drawdown_pct > 0 else None,
            profit_factor=(gross_profit / gross_loss_abs) if gross_loss_abs else None,
            expectancy_ratio=self._expectancy_ratio(wins, losses),
            win_rate=(len(wins) / len(trades) * 100.0) if trades else 0.0,
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            draws=len(draws),
            avg_trade_pct=(sum(trade.profit_pct for trade in trades) / len(trades)) if trades else None,
            avg_trade_duration_minutes=int(sum(trade.duration_minutes or 0 for trade in trades) / len(trades)) if trades else None,
            best_trade_pct=max((trade.profit_pct for trade in trades), default=None),
            worst_trade_pct=min((trade.profit_pct for trade in trades), default=None),
            pair_breakdown=self._pair_breakdown(trades, initial_cash),
        )

    def quote_currency(self, symbol: str) -> str:
        parts = symbol.split("/")
        if len(parts) != 2:
            raise ValueError(f"无效交易对: {symbol}")
        return parts[1].split(":")[0]

    def _pair_breakdown(self, trades: list[BacktestTradeRecord], initial_cash: float) -> list[BacktestPairBreakdownResponse]:
        grouped: dict[str, list[BacktestTradeRecord]] = {}
        for trade in trades:
            grouped.setdefault(trade.pair or "UNKNOWN", []).append(trade)
        result = []
        for pair, items in grouped.items():
            profit_abs = sum(item.profit_abs for item in items)
            wins = sum(1 for item in items if item.profit_abs > 0)
            result.append(
                BacktestPairBreakdownResponse(
                    pair=pair,
                    trades=len(items),
                    profit_abs=profit_abs,
                    profit_pct=(profit_abs / initial_cash * 100.0) if initial_cash else 0.0,
                    win_rate=(wins / len(items) * 100.0) if items else 0.0,
                )
            )
        return sorted(result, key=lambda item: item.profit_abs, reverse=True)

    def _equity_returns(self, equity_curve: list[BacktestEquityPointRecord]) -> list[float]:
        returns = []
        previous = None
        for point in equity_curve:
            if previous and previous.equity:
                returns.append((point.equity - previous.equity) / previous.equity)
            previous = point
        return returns

    def _sharpe_ratio(self, returns: list[float]) -> float | None:
        if len(returns) < 2:
            return None
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        if variance <= 0:
            return None
        return mean / math.sqrt(variance) * math.sqrt(len(returns))

    def _sortino_ratio(self, returns: list[float]) -> float | None:
        downside = [value for value in returns if value < 0]
        if not downside:
            return None
        mean = sum(returns) / len(returns)
        downside_mean = sum(downside) / len(downside)
        variance = sum((value - downside_mean) ** 2 for value in downside) / len(downside)
        if variance <= 0:
            return None
        return mean / math.sqrt(variance) * math.sqrt(len(returns))

    def _expectancy_ratio(self, wins: list[BacktestTradeRecord], losses: list[BacktestTradeRecord]) -> float | None:
        if not wins or not losses:
            return None
        avg_win = sum(item.profit_abs for item in wins) / len(wins)
        avg_loss = abs(sum(item.profit_abs for item in losses) / len(losses))
        if avg_loss == 0:
            return None
        win_rate = len(wins) / (len(wins) + len(losses))
        return ((win_rate * avg_win) - ((1 - win_rate) * avg_loss)) / avg_loss

    def _annualized_return_pct(self, initial_cash: float, final_balance: float, start_date: datetime, end_date: datetime) -> float | None:
        days = max((end_date - start_date).total_seconds() / 86_400.0, 0.0)
        if days <= 0 or initial_cash <= 0 or final_balance <= 0:
            return None
        return ((final_balance / initial_cash) ** (365.0 / days) - 1.0) * 100.0
