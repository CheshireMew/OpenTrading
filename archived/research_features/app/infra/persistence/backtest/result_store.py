from __future__ import annotations

from app.contracts.backtest import BacktestEquityPointRecord, BacktestTradeRecord
from app.infra.db.schema import BacktestEquityPoint, BacktestSignal, BacktestTrade
from utils.time_utils import to_utc_naive_datetime


def replace_run_rows(*, session, run_id: int, result, default_pair: str, clear_existing: bool) -> None:
    if clear_existing:
        session.query(BacktestSignal).filter(BacktestSignal.backtest_id == run_id).delete(synchronize_session=False)
        session.query(BacktestTrade).filter(BacktestTrade.backtest_id == run_id).delete(synchronize_session=False)
        session.query(BacktestEquityPoint).filter(BacktestEquityPoint.backtest_id == run_id).delete(synchronize_session=False)

    store_run_rows(
        session=session,
        run_id=run_id,
        signals=result.signals,
        trades=result.trades,
        equity_curve=result.equity_curve,
        default_pair=default_pair,
    )


def store_run_rows(*, session, run_id: int, signals, trades, equity_curve, default_pair: str) -> None:
    signal_rows = build_signal_rows(run_id=run_id, signals=signals)
    trade_rows = build_trade_rows(run_id=run_id, trades=trades, default_pair=default_pair)
    equity_rows = build_equity_rows(run_id=run_id, equity_curve=equity_curve)

    if signal_rows:
        session.bulk_save_objects(signal_rows)
    if trade_rows:
        session.bulk_save_objects(trade_rows)
    if equity_rows:
        session.bulk_save_objects(equity_rows)
    session.flush()


def build_signal_rows(*, run_id: int, signals) -> list[BacktestSignal]:
    return [
        BacktestSignal(
            backtest_id=run_id,
            timestamp=to_utc_naive_datetime(item.timestamp),
            price=item.price,
            signal=item.signal,
            confidence=item.confidence,
            indicators=item.indicators,
            reasoning=item.reasoning,
        )
        for item in signals
    ]


def build_trade_rows(*, run_id: int, trades, default_pair: str) -> list[BacktestTrade]:
    return [
        BacktestTrade(
            backtest_id=run_id,
            pair=item.pair or default_pair,
            opened_at=to_utc_naive_datetime(item.opened_at),
            closed_at=to_utc_naive_datetime(item.closed_at) if item.closed_at is not None else None,
            entry_price=item.entry_price,
            exit_price=item.exit_price,
            stake_amount=item.stake_amount,
            amount=item.amount,
            profit_abs=item.profit_abs,
            profit_pct=item.profit_pct,
            max_drawdown_pct=item.max_drawdown_pct,
            duration_minutes=item.duration_minutes,
            entry_tag=item.entry_tag,
            exit_reason=item.exit_reason,
            leverage=item.leverage,
            side=item.side,
        )
        for item in trades
    ]


def build_equity_rows(*, run_id: int, equity_curve) -> list[BacktestEquityPoint]:
    return [
        BacktestEquityPoint(
            backtest_id=run_id,
            timestamp=to_utc_naive_datetime(item.timestamp),
            equity=item.equity,
            pnl_abs=item.pnl_abs,
            drawdown_pct=item.drawdown_pct,
        )
        for item in equity_curve
    ]


def trade_record_from_row(item: BacktestTrade) -> BacktestTradeRecord:
    return BacktestTradeRecord(
        opened_at=item.opened_at,
        closed_at=item.closed_at,
        entry_price=item.entry_price,
        exit_price=item.exit_price,
        stake_amount=item.stake_amount,
        amount=item.amount,
        profit_abs=item.profit_abs,
        profit_pct=item.profit_pct,
        max_drawdown_pct=item.max_drawdown_pct,
        duration_minutes=item.duration_minutes,
        entry_tag=item.entry_tag,
        exit_reason=item.exit_reason,
        leverage=item.leverage,
        pair=item.pair,
        side=item.side,
    )


def equity_point_record_from_row(item: BacktestEquityPoint) -> BacktestEquityPointRecord:
    return BacktestEquityPointRecord(
        timestamp=item.timestamp,
        equity=item.equity,
        pnl_abs=item.pnl_abs,
        drawdown_pct=item.drawdown_pct,
    )


def result_signal_counts(result) -> tuple[int, int, int]:
    buy_count = sum(1 for item in result.signals if item.signal == "BUY")
    sell_count = sum(1 for item in result.signals if item.signal == "SELL")
    hold_count = max(int(result.total_candles) - len(result.signals), 0)
    return buy_count, sell_count, hold_count
