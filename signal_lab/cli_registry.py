from __future__ import annotations

import typer


app = typer.Typer(
    help="Auditable market history and dollar liquidity.",
    no_args_is_help=True,
)
data_app = typer.Typer(help="Market data refresh commands.")
jobs_app = typer.Typer(help="Auditable scheduled data and monitoring jobs.")
database_app = typer.Typer(help="OpenTrading data inventory.")
storage_app = typer.Typer(help="Managed runtime storage status and recovery candidates.")
instruments_app = typer.Typer(help="Canonical cross-asset instrument catalog.")
prices_app = typer.Typer(help="Auditable cross-asset daily price history.")
macro_app = typer.Typer(help="Auditable macroeconomic history.")
price_snapshots_app = typer.Typer(help="Verified offline price snapshot bundles.")
price_datasets_app = typer.Typer(help="Immutable partitioned price datasets.")
price_indicators_app = typer.Typer(help="Versioned technical indicator artifacts.")
classifications_app = typer.Typer(help="Point-in-time instrument classifications.")

app.add_typer(data_app, name="data")
app.add_typer(jobs_app, name="jobs")
app.add_typer(database_app, name="database")
app.add_typer(storage_app, name="storage")
app.add_typer(instruments_app, name="instruments")
app.add_typer(prices_app, name="prices")
app.add_typer(macro_app, name="macro")
prices_app.add_typer(price_snapshots_app, name="snapshots")
prices_app.add_typer(price_datasets_app, name="datasets")
prices_app.add_typer(price_indicators_app, name="indicators")
instruments_app.add_typer(classifications_app, name="classifications")
