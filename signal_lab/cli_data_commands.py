from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from signal_lab.cli_registry import data_app
from signal_lab.cli_support import parse_datetime
from signal_lab.config import SignalLabConfig
from signal_lab.storage.database import SignalLabDatabase


@data_app.command("crypto-sync")
def crypto_sync(
    symbols: Annotated[list[str], typer.Option("--symbol", help="Repeat for multiple symbols.")] = ["BTC/USDT", "ETH/USDT"],
    start: Annotated[str, typer.Option(help="ISO-8601 UTC start.")] = "2024-01-01T00:00:00Z",
    end: Annotated[str, typer.Option(help="ISO-8601 UTC end.")] = datetime.now(timezone.utc).isoformat(),
    root: Annotated[Path | None, typer.Option(help="Override SIGNAL_LAB_DATA_DIR.")] = None,
) -> None:
    from signal_lab.data.binance import BinanceDataClient
    from signal_lab.data.candles import resample_completed
    from signal_lab.storage.market import MarketDataStore

    store = MarketDataStore(SignalLabConfig.load().resolve_data_dir(root))
    client = BinanceDataClient()
    for symbol in symbols:
        series = client.sync(symbol, parse_datetime(start), parse_datetime(end), "15m")
        path = store.save(series)
        hourly_path = store.save(resample_completed(series, "1h"))
        typer.echo(f"{symbol}: {len(series.candles)} candles -> {path} ({series.price_source})")
        typer.echo(f"{symbol}: derived completed 1h candles -> {hourly_path}")
        if series.missing_ranges:
            typer.echo(f"warning: {len(series.missing_ranges)} missing ranges detected")


@data_app.command("liquidity-sync")
def liquidity_sync(
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    from signal_lab.macro import sync_liquidity_data

    """Refresh the public official inputs used by the dollar-liquidity monitor."""

    settings = SignalLabConfig.load()
    base = settings.resolve_data_dir(root)
    try:
        result = sync_liquidity_data(base, settings)
    except (OSError, RuntimeError, ValueError) as exc:
        raise typer.BadParameter(f"dollar-liquidity sync failed: {exc}") from exc
    typer.echo(
        f"liquidity: {result['series_count']} series, {result['row_count']} observations "
        f"-> {SignalLabDatabase(base).location}"
    )


