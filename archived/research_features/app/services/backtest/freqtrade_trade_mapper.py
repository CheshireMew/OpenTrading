from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.contracts.backtest import BacktestResearchConfig, BacktestSignalRecord, BacktestTradeRecord
from utils.time_utils import to_utc_naive_datetime


class FreqtradeTradeMapper:
    def build_trade_records(
        self,
        trades: pd.DataFrame,
        *,
        pair_aliases: dict[str, str] | None = None,
    ) -> list[BacktestTradeRecord]:
        if trades.empty:
            return []
        records = []
        for trade in trades.sort_values("open_date").to_dict("records"):
            closed_at = None
            if trade.get("close_date") is not None and not pd.isna(trade.get("close_date")):
                closed_at = to_utc_naive_datetime(trade["close_date"])
            side = "short" if bool(trade.get("is_short")) else "long"
            pair = trade.get("pair") or ""
            if pair_aliases and pair in pair_aliases:
                pair = pair_aliases[pair]
            records.append(
                BacktestTradeRecord(
                    opened_at=to_utc_naive_datetime(trade["open_date"]),
                    closed_at=closed_at,
                    entry_price=float(trade["open_rate"]),
                    exit_price=self._coerce_float(trade.get("close_rate")),
                    stake_amount=self._coerce_float(trade.get("stake_amount")) or 0.0,
                    amount=self._coerce_float(trade.get("amount")) or 0.0,
                    profit_abs=self._coerce_float(trade.get("profit_abs")) or 0.0,
                    profit_pct=(self._coerce_float(trade.get("profit_ratio")) or 0.0) * 100.0,
                    max_drawdown_pct=None,
                    duration_minutes=self._coerce_int(trade.get("trade_duration")),
                    entry_tag=trade.get("enter_tag"),
                    exit_reason=trade.get("exit_reason"),
                    leverage=self._coerce_float(trade.get("leverage")) or 1.0,
                    pair=pair,
                    side=side,
                )
            )
        return records

    def apply_execution_adjustments(
        self,
        trades: list[BacktestTradeRecord],
        research: BacktestResearchConfig,
        end_date: datetime,
    ) -> list[BacktestTradeRecord]:
        slippage_ratio = research.slippage_bps / 10_000.0
        adjusted = []
        for trade in trades:
            holding_end = trade.closed_at or end_date
            holding_days = max((holding_end - trade.opened_at).total_seconds() / 86_400.0, 0.0)
            leverage = max(trade.leverage, 1.0)
            slippage_abs = (trade.stake_amount or 0.0) * slippage_ratio * 2.0 * leverage
            funding_abs = (trade.stake_amount or 0.0) * leverage * (research.funding_rate_daily / 100.0) * holding_days
            adjusted_profit = trade.profit_abs - slippage_abs - funding_abs
            adjusted.append(
                BacktestTradeRecord(
                    opened_at=trade.opened_at,
                    closed_at=trade.closed_at,
                    entry_price=max(trade.entry_price * (1.0 + slippage_ratio), 1e-8) if trade.side == "long" else max(trade.entry_price * (1.0 - slippage_ratio), 1e-8),
                    exit_price=(
                        max(trade.exit_price * (1.0 - slippage_ratio), 1e-8)
                        if trade.side == "long"
                        else max(trade.exit_price * (1.0 + slippage_ratio), 1e-8)
                    ) if trade.exit_price is not None else None,
                    stake_amount=trade.stake_amount,
                    amount=trade.amount,
                    profit_abs=adjusted_profit,
                    profit_pct=(adjusted_profit / trade.stake_amount * 100.0) if trade.stake_amount else 0.0,
                    max_drawdown_pct=trade.max_drawdown_pct,
                    duration_minutes=trade.duration_minutes,
                    entry_tag=trade.entry_tag,
                    exit_reason=trade.exit_reason,
                    leverage=trade.leverage,
                    pair=trade.pair,
                    side=trade.side,
                )
            )
        return adjusted

    def build_signal_records(self, trades: list[BacktestTradeRecord]) -> list[BacktestSignalRecord]:
        signals = []
        for trade in sorted(trades, key=lambda item: item.opened_at):
            entry_signal = "BUY" if trade.side == "long" else "SELL"
            exit_signal = "SELL" if trade.side == "long" else "BUY"
            signals.append(
                BacktestSignalRecord(
                    timestamp=trade.opened_at,
                    price=trade.entry_price,
                    signal=entry_signal,
                    confidence=100.0,
                    indicators={
                        "pair": trade.pair,
                        "side": trade.side,
                        "trade_duration": trade.duration_minutes,
                        "profit_ratio": trade.profit_pct / 100.0,
                    },
                    reasoning=f"Freqtrade entry: {trade.entry_tag or ('long_entry_signal' if trade.side == 'long' else 'short_entry_signal')}",
                )
            )
            if trade.closed_at and trade.exit_price is not None:
                close_at = trade.closed_at if trade.closed_at > trade.opened_at else trade.closed_at + timedelta(seconds=1)
                signals.append(
                    BacktestSignalRecord(
                        timestamp=close_at,
                        price=trade.exit_price,
                        signal=exit_signal,
                        confidence=100.0,
                        indicators={
                            "pair": trade.pair,
                            "side": trade.side,
                            "profit_abs": trade.profit_abs,
                            "profit_ratio": trade.profit_pct / 100.0,
                        },
                        reasoning=f"Freqtrade exit: {trade.exit_reason or ('long_exit_signal' if trade.side == 'long' else 'short_exit_signal')}",
                    )
                )
        return signals

    def _coerce_float(self, value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    def _coerce_int(self, value: Any) -> int | None:
        if value is None or pd.isna(value):
            return None
        return int(value)
