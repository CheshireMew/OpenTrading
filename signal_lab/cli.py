from __future__ import annotations

import logging
import sys

import typer

from signal_lab.cli_registry import app

# Importing these modules registers their commands on the shared Typer registry.
from signal_lab import cli_operation_commands as _cli_operation_commands  # noqa: F401
from signal_lab import cli_price_commands as _cli_price_commands  # noqa: F401
from signal_lab import cli_data_commands as _cli_data_commands  # noqa: F401


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
    from signal_lab.config import SignalLabConfig
    from signal_lab.storage.database import bind_database

    runtime = build_database_runtime(settings)
    ctx.call_on_close(runtime.dispose)
    ctx.with_resource(bind_database(runtime.engine, SignalLabConfig.load().data_dir))


if __name__ == "__main__":
    app()
