from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import sys
from typing import Any

from app.contracts.data_health import DataRepairCommand
from app.contracts.portfolios import PortfolioAnalyticsCommand
from app.contracts.research import MarketScreenerRunCommand, ResearchReportGenerateCommand
from app.runtime import build_app_runtime_services


SCHEMA_VERSION = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Heimdall structured research CLI")
    subparsers = parser.add_subparsers(dest="resource", required=True)
    from scripts.local_backtest_cli import add_parser
    add_parser(subparsers)

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

    report = subparsers.add_parser("report", help="List or generate reproducible research reports")
    report.add_argument("action", choices=["list", "generate"])
    report.add_argument("--title", default="Heimdall Research Brief")
    report.add_argument(
        "--type", choices=["daily_brief", "weekly_brief", "asset_review", "portfolio_review", "decision_review"], default="daily_brief"
    )
    report.add_argument("--symbol")
    report.add_argument("--portfolio-id")
    report.add_argument("--limit", type=int, default=50)

    screener = subparsers.add_parser("screener", help="Run or replay a saved market screener")
    screener.add_argument("id")
    screener.add_argument("--as-of")

    portfolio = subparsers.add_parser("portfolio", help="Run portfolio performance and risk analysis")
    portfolio.add_argument("id")
    portfolio.add_argument("--period-days", type=int, default=365)
    portfolio.add_argument("--benchmark", default="BTC/USDT")
    portfolio.add_argument("--shock", action="append", default=[], metavar="SYMBOL=PCT")
    return parser


async def execute(args: argparse.Namespace) -> Any:
    if args.resource == "backtest":
        from scripts.local_backtest_cli import execute as execute_backtest
        return await execute_backtest(args)
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
        if args.resource == "report":
            if args.action == "generate":
                return await api.research_reports.generate(
                    ResearchReportGenerateCommand(
                        title=args.title, reportType=args.type, symbol=args.symbol, portfolioId=args.portfolio_id
                    )
                )
            return await asyncio.to_thread(
                api.research_reports.list_reports, include_archived=False, offset=0, limit=args.limit
            )
        if args.resource == "screener":
            as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else None
            return await api.market_screeners.run(args.id, MarketScreenerRunCommand(asOf=as_of))
        shocks = {}
        for value in args.shock:
            if "=" not in value:
                raise ValueError("--shock 必须使用 SYMBOL=PCT，例如 BTC/USDT=-30")
            symbol, percent = value.split("=", 1)
            shocks[symbol.strip().upper()] = float(percent)
        return await api.tools.portfolio_analytics.analyze(
            args.id,
            PortfolioAnalyticsCommand(periodDays=args.period_days, benchmarkSymbol=args.benchmark, customShocks=shocks),
        )
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
