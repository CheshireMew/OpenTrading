from __future__ import annotations

import logging
import sys

import typer

from scripts.market_data.registry import app

# Importing these modules registers their commands on the shared Typer registry.
from scripts.market_data import operation_commands as _cli_operation_commands  # noqa: F401
from scripts.market_data import price_commands as _cli_price_commands  # noqa: F401
from scripts.market_data import data_commands as _cli_data_commands  # noqa: F401


logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="%(levelname)s %(message)s",
)

__all__ = ["app"]


@app.callback()
def open_trading_database(ctx: typer.Context) -> None:
    from app.infra.db.database import build_database_runtime
    from config import settings
    from app.services.market_data_runtime import MarketDataRuntime

    runtime = build_database_runtime(settings)
    ctx.obj = MarketDataRuntime(runtime, settings)
    ctx.call_on_close(runtime.dispose)


if __name__ == "__main__":
    app()
