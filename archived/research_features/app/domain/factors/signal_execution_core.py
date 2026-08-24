from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.contracts.backtest import BacktestEquityPointRecord, BacktestSignalRecord, BacktestTradeRecord


@dataclass(slots=True)
class FactorSignalPosition:
    opened_at: datetime
    entry_price: float
    amount: float
    stake_amount: float
    entry_score: float
    highest_price: float
    last_price: float


@dataclass(slots=True)
class FactorSignalState:
    cash_balance: float
    held_bars: int = 0
    position: FactorSignalPosition | None = None


@dataclass(slots=True)
class FactorSignalContext:
    symbol: str
    research_run_id: int
    initial_cash: float
    fee_rate: float
    position_size_pct: float
    stake_mode: str
    entry_threshold: float
    exit_threshold: float
    stoploss_pct: float
    takeprofit_pct: float
    max_hold_bars: int


@dataclass(slots=True)
class FactorSignalBatch:
    state: FactorSignalState
    signals: list[BacktestSignalRecord] = field(default_factory=list)
    trades: list[BacktestTradeRecord] = field(default_factory=list)
    equity_points: list[BacktestEquityPointRecord] = field(default_factory=list)


class FactorSignalExecutionCore:
    def create_state(self, initial_cash: float, *, position: FactorSignalPosition | None = None, held_bars: int = 0) -> FactorSignalState:
        return FactorSignalState(
            cash_balance=float(initial_cash),
            held_bars=max(int(held_bars or 0), 0),
            position=position,
        )

    def run_batch(
        self,
        *,
        rows: list[dict[str, Any]],
        state: FactorSignalState,
        context: FactorSignalContext,
        force_close: bool = False,
    ) -> FactorSignalBatch:
        signals: list[BacktestSignalRecord] = []
        trades: list[BacktestTradeRecord] = []
        equity_points: list[BacktestEquityPointRecord] = []
        fee_ratio = context.fee_rate / 100.0

        for row in rows:
            price = float(row["close"])
            score = float(row.get("composite_score") or 0.0)
            timestamp = row["timestamp"]
            future_return = row.get("future_return")

            if state.position:
                state.position.last_price = price
                state.position.highest_price = max(state.position.highest_price, price)
                state.held_bars = max(state.held_bars + 1, 1)
                profit_ratio = self._profit_ratio(state.position, price, fee_ratio)
                if (
                    profit_ratio <= context.stoploss_pct
                    or profit_ratio >= context.takeprofit_pct
                    or score <= context.exit_threshold
                    or state.held_bars >= context.max_hold_bars
                ):
                    trade = self._close_position(state.position, price, timestamp, fee_ratio, context.symbol)
                    state.cash_balance += trade.stake_amount + trade.profit_abs
                    trades.append(trade)
                    signals.append(
                        self._build_signal(
                            timestamp=timestamp,
                            price=price,
                            signal="SELL",
                            score=score,
                            future_return=future_return,
                            research_run_id=context.research_run_id,
                            reasoning="Factor blend exit",
                        )
                    )
                    state.position = None
                    state.held_bars = 0

            if state.position is None and score >= context.entry_threshold:
                stake_amount = min(
                    state.cash_balance,
                    context.initial_cash * (context.position_size_pct / 100.0)
                    if context.stake_mode == "fixed"
                    else state.cash_balance * (context.position_size_pct / 100.0),
                )
                if stake_amount > 0:
                    notional = stake_amount / (1.0 + fee_ratio) if fee_ratio < 1 else 0.0
                    amount = notional / price if price > 0 else 0.0
                    if amount > 0:
                        state.cash_balance -= stake_amount
                        state.position = FactorSignalPosition(
                            opened_at=timestamp,
                            entry_price=price,
                            amount=amount,
                            stake_amount=stake_amount,
                            entry_score=score,
                            highest_price=price,
                            last_price=price,
                        )
                        state.held_bars = 0
                        signals.append(
                            self._build_signal(
                                timestamp=timestamp,
                                price=price,
                                signal="BUY",
                                score=score,
                                future_return=future_return,
                                research_run_id=context.research_run_id,
                                reasoning="Factor blend entry",
                            )
                        )

            equity = state.cash_balance
            if state.position:
                equity += state.position.amount * price * (1.0 - fee_ratio)
            equity_points.append(
                BacktestEquityPointRecord(
                    timestamp=timestamp,
                    equity=equity,
                    pnl_abs=equity - context.initial_cash,
                    drawdown_pct=0.0,
                )
            )

        if force_close and state.position and rows:
            last_row = rows[-1]
            trade = self._close_position(
                state.position,
                float(last_row["close"]),
                last_row["timestamp"],
                fee_ratio,
                context.symbol,
                exit_reason="force_close",
            )
            state.cash_balance += trade.stake_amount + trade.profit_abs
            trades.append(trade)
            signals.append(
                self._build_signal(
                    timestamp=last_row["timestamp"],
                    price=float(last_row["close"]),
                    signal="SELL",
                    score=float(last_row.get("composite_score") or 0.0),
                    future_return=last_row.get("future_return"),
                    research_run_id=context.research_run_id,
                    reasoning="Factor blend force close",
                )
            )
            state.position = None
            state.held_bars = 0
            if equity_points:
                equity_points[-1] = BacktestEquityPointRecord(
                    timestamp=last_row["timestamp"],
                    equity=state.cash_balance,
                    pnl_abs=state.cash_balance - context.initial_cash,
                    drawdown_pct=0.0,
                )

        return FactorSignalBatch(
            state=state,
            signals=signals,
            trades=trades,
            equity_points=equity_points,
        )

    def serialize_position(self, position: FactorSignalPosition | None, *, symbol: str) -> dict[str, Any] | None:
        if not position:
            return None
        return {
            "symbol": symbol,
            "opened_at": position.opened_at.isoformat(),
            "entry_price": position.entry_price,
            "remaining_amount": position.amount,
            "remaining_cost": position.stake_amount,
            "highest_price": position.highest_price,
            "last_price": position.last_price,
            "taken_partial_ids": [],
            "entry_score": position.entry_score,
        }

    def deserialize_position(self, payload: dict[str, Any] | None) -> FactorSignalPosition | None:
        if not payload:
            return None
        return FactorSignalPosition(
            opened_at=datetime.fromisoformat(payload["opened_at"]),
            entry_price=float(payload["entry_price"]),
            amount=float(payload.get("remaining_amount", payload.get("amount", 0.0))),
            stake_amount=float(payload.get("remaining_cost", payload.get("stake_amount", 0.0))),
            entry_score=float(payload.get("entry_score", 0.0)),
            highest_price=float(payload.get("highest_price", payload.get("entry_price", 0.0))),
            last_price=float(payload.get("last_price", payload.get("entry_price", 0.0))),
        )

    def _build_signal(
        self,
        *,
        timestamp: datetime,
        price: float,
        signal: str,
        score: float,
        future_return: float | None,
        research_run_id: int,
        reasoning: str,
    ) -> BacktestSignalRecord:
        indicators: dict[str, Any] = {
            "composite_score": score,
            "research_run_id": research_run_id,
        }
        if future_return is not None:
            indicators["future_return"] = float(future_return)
        return BacktestSignalRecord(
            timestamp=timestamp,
            price=price,
            signal=signal,
            confidence=100.0,
            indicators=indicators,
            reasoning=reasoning,
        )

    def _profit_ratio(self, position: FactorSignalPosition, price: float, fee_ratio: float) -> float:
        net_value = position.amount * price * (1.0 - fee_ratio)
        if position.stake_amount <= 0:
            return 0.0
        return (net_value - position.stake_amount) / position.stake_amount

    def _close_position(
        self,
        position: FactorSignalPosition,
        price: float,
        timestamp: datetime,
        fee_ratio: float,
        symbol: str,
        exit_reason: str = "factor_exit",
    ) -> BacktestTradeRecord:
        gross = position.amount * price
        net = gross * (1.0 - fee_ratio)
        profit_abs = net - position.stake_amount
        duration_minutes = max(int((timestamp - position.opened_at).total_seconds() // 60), 0)
        return BacktestTradeRecord(
            opened_at=position.opened_at,
            closed_at=timestamp,
            entry_price=position.entry_price,
            exit_price=price,
            stake_amount=position.stake_amount,
            amount=position.amount,
            profit_abs=profit_abs,
            profit_pct=(profit_abs / position.stake_amount * 100.0) if position.stake_amount else 0.0,
            duration_minutes=duration_minutes,
            entry_tag="factor_entry",
            exit_reason=exit_reason,
            leverage=1.0,
            pair=symbol,
        )
