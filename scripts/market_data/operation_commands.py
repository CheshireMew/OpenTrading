from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from config.market_data import MarketDataConfig
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.projections import DatabaseProjection
from app.infra.structured_data import dumps_json
from scripts.market_data.registry import app, database_app, jobs_app, storage_app


@app.command("migrate")
def migrate(
    source: Annotated[Path, typer.Option(exists=True, file_okay=False, help="Legacy .data directory.")],
    apply: Annotated[bool, typer.Option("--apply", help="Copy files and commit records.")] = False,
) -> None:
    """Inspect or import legacy market and liquidity data into OpenTrading."""
    from app.infra.persistence.market.history.import_legacy import import_legacy_data

    config = MarketDataConfig.load()
    try:
        result = import_legacy_data(source, config.data_dir, apply=apply)
    except (OSError, ValueError) as exc:
        typer.echo(dumps_json({"status": "error", "message": str(exc)}))
        raise typer.Exit(1) from exc
    typer.echo(dumps_json(result))


@jobs_app.command("add")
def jobs_add(
    job_id: Annotated[str, typer.Option("--id")],
    task: Annotated[str, typer.Option(help="liquidity_refresh")],
    every_minutes: Annotated[int, typer.Option(min=1)] = 1440,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Add a persistent interval job."""

    from app.services.market.history_jobs import JobScheduler

    settings = MarketDataConfig.load()
    scheduler = JobScheduler(settings, settings.resolve_data_dir(root))
    try:
        job = scheduler.add(job_id, task, every_minutes)
    except (ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"job={job.job_id} task={job.task} every={job.interval_minutes}m enabled")


@jobs_app.command("enable")
def jobs_enable(
    job_id: Annotated[str, typer.Option("--id")],
    enabled: Annotated[bool, typer.Option("--enabled/--disabled")] = True,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Enable or disable an existing job without deleting its history."""

    from app.services.market.history_jobs import JobScheduler

    settings = MarketDataConfig.load()
    scheduler = JobScheduler(settings, settings.resolve_data_dir(root))
    try:
        job = scheduler.set_enabled(job_id, enabled)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"job={job.job_id} {'enabled' if job.enabled else 'disabled'}")


@jobs_app.command("run")
def jobs_run(
    job_id: Annotated[str, typer.Option("--id")],
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Run one job now and persist its result."""

    from app.services.market.history_jobs import JobScheduler

    settings = MarketDataConfig.load()
    scheduler = JobScheduler(settings, settings.resolve_data_dir(root))
    try:
        result = scheduler.run(job_id)
    except (ValueError, RuntimeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"{result.status.upper()} {result.run_id}: {result.summary}")
    if result.status in {"blocked", "error"}:
        raise typer.Exit(code=1)


@jobs_app.command("run-due")
def jobs_run_due(
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Run every enabled job whose interval has elapsed."""

    from app.services.market.history_jobs import JobScheduler

    settings = MarketDataConfig.load()
    scheduler = JobScheduler(settings, settings.resolve_data_dir(root))
    results = scheduler.run_due()
    if not results:
        typer.echo("no jobs due")
        return
    for result in results:
        typer.echo(f"{result.status.upper()} {result.job_id}: {result.summary}")
    if any(item.status in {"blocked", "error"} for item in results):
        raise typer.Exit(code=1)


@jobs_app.command("watch")
def jobs_watch(
    poll_seconds: Annotated[int, typer.Option(min=1, max=60)] = 30,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Keep running due jobs until interrupted."""

    from time import sleep
    from app.services.market.history_jobs import JobScheduler

    settings = MarketDataConfig.load()
    scheduler = JobScheduler(settings, settings.resolve_data_dir(root))
    typer.echo(f"watching {len(scheduler.jobs())} jobs; poll={poll_seconds}s")
    try:
        while True:
            for result in scheduler.run_due():
                typer.echo(f"{result.status.upper()} {result.job_id}: {result.summary}")
            sleep(poll_seconds)
    except KeyboardInterrupt:
        typer.echo("stopped")


@jobs_app.command("status")
def jobs_status(
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Show configured jobs and their last persisted result."""

    from app.services.market.history_jobs import JobScheduler

    settings = MarketDataConfig.load()
    scheduler = JobScheduler(settings, settings.resolve_data_dir(root))
    jobs = scheduler.jobs()
    if not jobs:
        typer.echo("no jobs configured")
        return
    for job in jobs:
        latest = scheduler.latest(job.job_id)
        last = f"{latest.status} {latest.started_at}" if latest else "never"
        typer.echo(
            f"job={job.job_id} task={job.task} every={job.interval_minutes}m "
            f"enabled={job.enabled} last={last}"
        )


@jobs_app.command("events")
def jobs_events(
    correlation_id: Annotated[str, typer.Option("--correlation-id")],
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 200,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Read the persisted event chain for one job run or HTTP mutation."""

    from app.infra.persistence.market.history.operations import OperationRepository

    base = MarketDataConfig.load().resolve_data_dir(root)
    events = OperationRepository(MarketHistoryDatabase(base)).events(
        correlation_id=correlation_id,
        limit=limit,
    )
    typer.echo(dumps_json(
        {
            "schema_version": "signal-lab.operation-events.v1",
            "correlation_id": correlation_id,
            "events": events,
        },
        compact=True,
    ))


@database_app.command("status")
def database_status(
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    base = MarketDataConfig.load().resolve_data_dir(root)
    summary = DatabaseProjection(MarketHistoryDatabase(base)).summary()
    typer.echo(f"database={summary['path']} schema={summary['schema_version']} bytes={summary['size_bytes']}")
    for key, value in summary["counts"].items():
        typer.echo(f"{key}={value}")


@storage_app.command("status")
def storage_status(
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    from app.infra.persistence.market.history.capacity import ManagedStorage

    settings = MarketDataConfig.load()
    base = settings.resolve_data_dir(root)
    payload = ManagedStorage(
        base,
        maximum_managed_bytes=settings.max_managed_bytes,
        minimum_free_bytes=settings.min_free_bytes,
    ).status()
    typer.echo(dumps_json(payload))
