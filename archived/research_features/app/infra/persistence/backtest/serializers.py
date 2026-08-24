from __future__ import annotations

from app.infra.db.schema import BacktestEquityPoint, BacktestRun, BacktestSignal, BacktestTrade
from app.contracts.backtest_run import serialize_run_metadata


def serialize_backtest_metadata(run: BacktestRun) -> dict:
    return serialize_run_metadata(
        run.metadata_info,
        execution_mode=run.execution_mode,
        engine=run.engine,
    )


def serialize_backtest_run(run: BacktestRun, include_signals: bool = False) -> dict:
    metadata = serialize_backtest_metadata(run)
    data = {
        "id": run.id,
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "start_date": run.start_date.isoformat() if run.start_date else None,
        "end_date": run.end_date.isoformat() if run.end_date else None,
        "status": run.status,
        "metadata": metadata,
        "report": metadata.get("report"),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "metrics": {
            "total_candles": run.total_candles,
            "total_signals": run.total_signals,
            "buy_signals": run.buy_signals,
            "sell_signals": run.sell_signals,
            "hold_signals": run.hold_signals,
        },
    }
    if include_signals and run.signals:
        data["signals"] = [serialize_backtest_signal(signal) for signal in run.signals]
    return data


def serialize_backtest_signal(signal: BacktestSignal) -> dict:
    return {
        "id": signal.id,
        "timestamp": signal.timestamp.isoformat() if signal.timestamp else None,
        "price": signal.price,
        "signal": signal.signal,
        "confidence": signal.confidence,
        "indicators": signal.indicators,
        "reasoning": signal.reasoning,
    }


def serialize_backtest_trade(trade: BacktestTrade) -> dict:
    return {
        "id": trade.id,
        "pair": trade.pair,
        "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
        "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "stake_amount": trade.stake_amount,
        "amount": trade.amount,
        "profit_abs": trade.profit_abs,
        "profit_pct": trade.profit_pct,
        "max_drawdown_pct": trade.max_drawdown_pct,
        "duration_minutes": trade.duration_minutes,
        "entry_tag": trade.entry_tag,
        "exit_reason": trade.exit_reason,
        "leverage": trade.leverage,
        "side": trade.side,
    }


def serialize_backtest_equity_point(point: BacktestEquityPoint) -> dict:
    return {
        "id": point.id,
        "timestamp": point.timestamp.isoformat() if point.timestamp else None,
        "equity": point.equity,
        "pnl_abs": point.pnl_abs,
        "drawdown_pct": point.drawdown_pct,
    }
