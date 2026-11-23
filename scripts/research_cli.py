from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import sys
import logging
from contextlib import contextmanager, redirect_stdout
from typing import Any

from app.contracts.data_health import DataRepairCommand
from app.contracts.research import MarketScreenerRunCommand
from app.runtime import build_app_runtime_services


SCHEMA_VERSION = 1


@contextmanager
def diagnostic_output():
    """Keep library logs/prints off the machine-readable stdout channel."""
    redirected = []
    loggers = [logging.getLogger(), *logging.Logger.manager.loggerDict.values()]
    for logger in loggers:
        if isinstance(logger, logging.Logger):
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
                    redirected.append((handler, handler.stream))
                    handler.setStream(sys.stderr)
    try:
        with redirect_stdout(sys.stderr):
            yield
    finally:
        for handler, stream in redirected:
            handler.setStream(stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenTrading structured research CLI")
    subparsers = parser.add_subparsers(dest="resource", required=True)

    health = subparsers.add_parser("health", help="Inspect or repair data health")
    health.add_argument(
        "--repair",
        choices=[
            "verify_database",
            "refresh_binance_snapshot",
            "hydrate_symbol_history",
            "evaluate_research_alerts",
            "evaluate_trade_signals",
        ],
    )
    health.add_argument("--symbol")
    health.add_argument("--timeframe", default="1h")
    health.add_argument("--days", type=int, default=365)

    asset = subparsers.add_parser("asset", help="Build a unified asset snapshot")
    asset.add_argument("symbol")
    asset.add_argument("--timeframe", default="1h")
    asset.add_argument("--history-days", type=int, default=365)

    signals = subparsers.add_parser("signals", help="List or evaluate trade signals")
    signals.add_argument("action", choices=["list", "evaluate"])
    signals.add_argument("--symbol")
    signals.add_argument("--outcome")
    signals.add_argument("--source")
    signals.add_argument("--signal-id")
    signals.add_argument("--limit", type=int, default=100)

    screener = subparsers.add_parser("screener", help="Run or replay a saved market screener")
    screener.add_argument("id")
    screener.add_argument("--as-of")

    return parser


async def execute(args: argparse.Namespace) -> Any:
    runtime = await asyncio.to_thread(build_app_runtime_services, "api")
    api = runtime.require_api()
    try:
        if args.resource == "health":
            if args.repair:
                return await api.data_health.repair(
                    DataRepairCommand(action=args.repair, symbol=args.symbol, timeframe=args.timeframe, days=args.days)
                )
            return await api.data_health.get_health()
        if args.resource == "asset":
            return await api.asset_research.get_asset(
                symbol=args.symbol, timeframe=args.timeframe, history_days=args.history_days
            )
        if args.resource == "signals":
            if args.action == "evaluate":
                return await api.trade_signal_evaluations.evaluate_once(signal_id=args.signal_id, force=True)
            return await asyncio.to_thread(
                api.trade_signals.list_signals,
                symbol=args.symbol,
                outcome_status=args.outcome,
                source=args.source,
                include_archived=False,
                offset=0,
                limit=args.limit,
            )
        if args.resource == "screener":
            as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else None
            return await api.market_screeners.run(args.id, MarketScreenerRunCommand(asOf=as_of))
        raise ValueError(f"Unknown research command: {args.resource}")
    finally:
        await runtime.shutdown()


def serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        with diagnostic_output():
            data = asyncio.run(execute(args))
        payload = {"schemaVersion": SCHEMA_VERSION, "ok": True, "command": args.resource, "data": serialize(data)}
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "ok": False,
            "command": getattr(args, "resource", None),
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
