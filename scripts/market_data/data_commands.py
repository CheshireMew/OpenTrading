from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from scripts.market_data.support import market_runtime
from scripts.market_data.registry import data_app
from scripts.market_data.support import parse_datetime
from app.infra.structured_data import dumps_json
from app.services.market.crypto_history_sync import CryptoHistorySync


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


