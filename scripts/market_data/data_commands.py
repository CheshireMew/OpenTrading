from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Annotated

import typer

from scripts.market_data.support import market_runtime
from scripts.market_data.registry import data_app
from scripts.market_data.support import parse_datetime
from app.infra.structured_data import dumps_json
from app.services.market.crypto_history_sync import CryptoHistorySync


@data_app.command("index-sync")
def index_sync(
    ctx: typer.Context,
    symbols: Annotated[list[str] | None, typer.Option("--symbol",help="Repeat to select indices; default: all existing indices.")] = None,
    timeframes: Annotated[list[str] | None, typer.Option("--timeframe",help="Repeat to select periods; default: all supported periods.")] = None,
    start: Annotated[str | None, typer.Option(help="UTC start; never earlier than the official launch.")] = None,
    end: Annotated[str | None, typer.Option(help="UTC end, defaulting to now.")] = None,
) -> None:
    """Save free published index history; exclude all pre-launch back series."""
    from app.domain.market.index_catalog import INDEX_CATALOG
    from app.services.market.index_history_sync import IndexHistorySync
    from utils.logger import logger
    results,warnings=[],[]
    first=parse_datetime(start) if start else None
    last=parse_datetime(end) if end else None
    # Third-party daily readers sometimes print login/status messages. Keep
    # stdout a single result document even when those fallbacks are used.
    output=sys.stdout
    with ExitStack() as cleanup, redirect_stdout(sys.stderr):
        for handler in logger.handlers:
            if getattr(handler,"stream",None) is output:
                handler.setStream(sys.stderr)
                cleanup.callback(handler.setStream,output)
        with IndexHistorySync(ctx.obj.database_runtime,
            progress=lambda item:typer.echo(dumps_json(item,compact=True),err=True)) as service:
            for symbol in symbols or INDEX_CATALOG:
                try:
                    results.append(service.sync(symbol,timeframes=timeframes,start=first,end=last))
                except Exception as exc:
                    warnings.append({"symbol":symbol,"error":str(exc)})
    success=not warnings and all(result["status"]=="saved" for result in results)
    typer.echo(dumps_json({"schema_version":"opentrading.index-sync.v1",
        "status":"saved" if success else "partial","results":results,"warnings":warnings},compact=True))
    if not success:
        raise typer.Exit(1)


@data_app.command("crypto-sync")
def crypto_sync(
    ctx: typer.Context,
    symbols: Annotated[list[str], typer.Option("--symbol", help="Repeat for multiple symbols.")] = ["BTC/USDT", "ETH/USDT"],
    start: Annotated[str, typer.Option(help="ISO-8601 UTC start.")] = "2024-01-01T00:00:00Z",
    end: Annotated[str | None, typer.Option(help="ISO-8601 UTC end, defaulting to now.")] = None,
) -> None:
    """Hydrate shared confirmed klines; repeated calls reuse stored history."""
    results, warnings = [], []
    try:
        first = parse_datetime(start)
        last = parse_datetime(end) if end else datetime.now(timezone.utc)
        with CryptoHistorySync(ctx.obj.database_runtime) as service:
            for symbol in symbols:
                results.append(service.sync(symbol, first, last))
    except Exception as exc:
        warnings.append(str(exc))
    complete = not warnings and all(item["status"] == "complete" for item in results)
    typer.echo(dumps_json({"schema_version": "opentrading.crypto-sync.v1",
                          "status": "complete" if complete else "partial" if results else "error",
                          "results": results, "warnings": warnings}, compact=True))
    if not complete:
        raise typer.Exit(1)


@data_app.command("liquidity-sync")
def liquidity_sync(
    ctx: typer.Context,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    from app.services.market.liquidity import sync_liquidity_data

    """Refresh the public official inputs used by the dollar-liquidity monitor."""

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        result = sync_liquidity_data(runtime.database, settings)
    except (OSError, RuntimeError, ValueError) as exc:
        raise typer.BadParameter(f"dollar-liquidity sync failed: {exc}") from exc
    typer.echo(
        f"liquidity: {result['series_count']} series, {result['row_count']} observations "
        f"-> {runtime.database.location}"
    )


