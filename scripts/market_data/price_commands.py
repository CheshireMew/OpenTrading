from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from scripts.market_data.support import market_runtime
from scripts.market_data.registry import (
    classifications_app,
    instruments_app,
    macro_app,
    price_datasets_app,
    price_indicators_app,
    price_snapshots_app,
    prices_app,
)
from scripts.market_data.support import (
    command_error as _command_error,
    dataset_instrument_selection as _dataset_instrument_selection,
    date_option as _date_option,
    emit_json as _emit_json,
    history_service as _history_service,
    operation_error as _operation_error,
)
from app.contracts.market_data import history_envelope


PERIOD_HELP = "Date range: 1mo, 3mo, 6mo, 1y, 3y, 5y, 10y, or max."


@instruments_app.command("sync")
def instruments_sync(
    ctx: typer.Context,
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
    remote: Annotated[bool, typer.Option("--remote/--seed-only", help="Include AKShare's live A-share directory.")] = True,
) -> None:
    from app.services.market.history.catalog import sync_instrument_catalog

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        result = sync_instrument_catalog(runtime.database, include_remote=remote)
        payload = history_envelope(
            "ok" if result["complete"] else "partial",
            {"command": "instruments.sync", "remote": remote},
            instrument={
                "catalog": {
                    "instrument_count": result["instrument_count"],
                    "alias_count": result["alias_count"],
                }
            },
            source={
                "selected": "instrument_catalog" if remote else "built_in_seed",
                "attempts": result["attempts"],
            },
            warnings=result["warnings"],
        )
    except Exception as exc:
        payload = _command_error("instruments.sync", str(exc))
    _emit_json(payload)


@instruments_app.command("resolve")
def instruments_resolve(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Name, alias or canonical instrument code.")],
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:
    from app.services.market.history.catalog import instrument_payload, resolve_instrument

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        matches = resolve_instrument(runtime.database, query)
        status = "ok" if len(matches) == 1 else "ambiguous" if len(matches) > 1 else "error"
        instrument = instrument_payload(matches[0]) if len(matches) == 1 else {
            "query": query, "candidates": [instrument_payload(item) for item in matches],
        }
        warnings = [] if matches else [f"instrument could not be resolved: {query}"]
        if len(matches) > 1:
            warnings.append("instrument name matches multiple assets; use a canonical code")
        payload = history_envelope(
            status,
            {"command": "instruments.resolve", "query": query},
            instrument=instrument,
            source={"selected": "instrument_catalog", "attempts": []},
            warnings=warnings,
        )
    except Exception as exc:
        payload = _command_error("instruments.resolve", str(exc))
    _emit_json(payload)


@prices_app.command("history")
def prices_history(
    ctx: typer.Context,
    instrument: Annotated[str, typer.Option("--instrument")],
    period: Annotated[str | None, typer.Option(help=PERIOD_HELP)] = None,
    start: Annotated[str | None, typer.Option()] = None,
    end: Annotated[str | None, typer.Option()] = None,
    basis: Annotated[str | None, typer.Option(help="raw, adjusted or both.")] = None,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    cache_only: Annotated[bool, typer.Option("--cache-only")] = False,
    provider: Annotated[str | None, typer.Option()] = None,
    export: Annotated[str | None, typer.Option(help="csv or json.")] = None,
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:
    try:
        if basis not in {None, "raw", "adjusted", "both"}:
            raise ValueError("basis must be raw, adjusted or both")
        if export not in {None, "csv", "json"}:
            raise ValueError("export must be csv or json")
        service, _, _ = _history_service(ctx, root)
        payload = service.history(
            instrument, period=period, start=_date_option(start, "start"), end=_date_option(end, "end"),
            basis=cast(Any, basis), refresh=refresh, cache_only=cache_only,
            provider=provider, export=cast(Any, export),
        )
    except Exception as exc:
        payload = _command_error("prices.history", str(exc))
    _emit_json(payload)


@prices_app.command("point")
def prices_point(
    ctx: typer.Context,
    instrument: Annotated[str, typer.Option("--instrument")],
    observation_date: Annotated[str, typer.Option("--date")],
    policy: Annotated[str, typer.Option(help="exact or on-or-before.")] = "on-or-before",
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    cache_only: Annotated[bool, typer.Option("--cache-only")] = False,
    provider: Annotated[str | None, typer.Option()] = None,
    export: Annotated[str | None, typer.Option(help="csv or json.")] = None,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    try:
        if policy not in {"exact", "on-or-before"}:
            raise ValueError("policy must be exact or on-or-before")
        if export not in {None, "csv", "json"}:
            raise ValueError("export must be csv or json")
        service, _, _ = _history_service(ctx, root)
        payload = service.point(
            instrument, cast(date, _date_option(observation_date, "date")),
            policy=cast(Any, policy), refresh=refresh, cache_only=cache_only,
            provider=provider, export=cast(Any, export),
        )
    except Exception as exc:
        payload = _command_error("prices.point", str(exc))
    _emit_json(payload)


@prices_app.command("update")
def prices_update(
    ctx: typer.Context,
    instrument: Annotated[str, typer.Option("--instrument")],
    start: Annotated[str | None, typer.Option(help="Required only for the first snapshot.")] = None,
    end: Annotated[str | None, typer.Option()] = None,
    basis: Annotated[str | None, typer.Option(help="raw, adjusted or both.")] = None,
    provider: Annotated[str | None, typer.Option()] = None,
    export: Annotated[str | None, typer.Option(help="csv or json.")] = None,
    overlap_days: Annotated[int, typer.Option(min=1, max=366)] = 14,
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:
    try:
        if basis not in {None, "raw", "adjusted", "both"}:
            raise ValueError("basis must be raw, adjusted or both")
        if export not in {None, "csv", "json"}:
            raise ValueError("export must be csv or json")
        service, _, _ = _history_service(ctx, root)
        payload = service.update(
            instrument,
            start=_date_option(start, "start"),
            end=_date_option(end, "end"),
            basis=cast(Any, basis),
            provider=provider,
            export=cast(Any, export),
            overlap_days=overlap_days,
        )
    except Exception as exc:
        payload = _command_error("prices.update", str(exc))
    _emit_json(payload)


@price_snapshots_app.command("export")
def price_snapshots_export(
    ctx: typer.Context,
    destination: Annotated[Path, typer.Option("--destination", file_okay=False)],
    snapshot_hashes: Annotated[list[str], typer.Option("--snapshot-hash")] = [],
    instruments: Annotated[list[str], typer.Option("--instrument")] = [],
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        payload = runtime.bundles.export_bundle(
            destination,
            snapshot_hashes=snapshot_hashes or None,
            instruments=instruments or None,
        )
    except Exception as exc:
        payload = _operation_error("prices.snapshots.export", str(exc))
    _emit_json(payload)


@price_snapshots_app.command("inspect")
def price_snapshots_inspect(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Option("--bundle", exists=True, file_okay=False)],
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        payload = runtime.bundles.inspect_bundle(bundle)
    except Exception as exc:
        payload = _operation_error("prices.snapshots.inspect", str(exc))
    _emit_json(payload)


@price_snapshots_app.command("import")
def price_snapshots_import(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Option("--bundle", exists=True, file_okay=False)],
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        payload = runtime.bundles.import_bundle(bundle)
    except Exception as exc:
        payload = _operation_error("prices.snapshots.import", str(exc))
    _emit_json(payload)


@price_datasets_app.command("build")
def price_datasets_build(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name")],
    start: Annotated[str, typer.Option()],
    end: Annotated[str, typer.Option()],
    instruments: Annotated[list[str] | None, typer.Option("--instrument")] = None,
    instruments_file: Annotated[
        Path | None,
        typer.Option("--instruments-file", exists=True, dir_okay=False),
    ] = None,
    all_cached: Annotated[bool, typer.Option("--all-cached")] = False,
    basis: Annotated[str, typer.Option(help="raw or adjusted.")] = "adjusted",
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    cache_only: Annotated[bool, typer.Option("--cache-only")] = False,
    provider: Annotated[str | None, typer.Option()] = None,
    include_indicators: Annotated[bool, typer.Option("--indicators/--no-indicators")] = True,
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        if basis not in {"raw", "adjusted"}:
            raise ValueError("basis must be raw or adjusted")
        if refresh and cache_only:
            raise ValueError("--refresh and --cache-only are mutually exclusive")
        selected = _dataset_instrument_selection(
            runtime.database, instruments, instruments_file, all_cached,
        )
        payload = runtime.datasets.build(
            name,
            selected,
            start=cast(date, _date_option(start, "start")),
            end=cast(date, _date_option(end, "end")),
            basis=cast(Any, basis),
            refresh=refresh,
            cache_only=cache_only,
            provider=provider,
            include_indicators=include_indicators,
        )
    except Exception as exc:
        payload = _operation_error("prices.datasets.build", str(exc))
    _emit_json(payload)


@price_indicators_app.command("materialize")
def price_indicators_materialize(
    ctx: typer.Context,
    instrument: Annotated[str, typer.Option("--instrument")],
    snapshot_hash: Annotated[str | None, typer.Option("--snapshot-hash")] = None,
    basis: Annotated[str, typer.Option(help="raw or adjusted.")] = "raw",
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:
    from app.services.market.history.catalog import resolve_instrument

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        if basis not in {"raw", "adjusted"}:
            raise ValueError("basis must be raw or adjusted")
        matches = resolve_instrument(runtime.database, instrument)
        if len(matches) != 1:
            raise ValueError(f"instrument must resolve uniquely: {instrument}")
        payload = {
            "status": "ok",
            **runtime.indicators.materialize(
                matches[0].canonical_code,
                snapshot_hash=snapshot_hash,
                basis=cast(Any, basis),
            ),
        }
    except Exception as exc:
        payload = _operation_error("prices.indicators.materialize", str(exc))
    _emit_json(payload)


@classifications_app.command("import")
def classifications_import(
    ctx: typer.Context,
    source: Annotated[Path, typer.Option("--file", exists=True, dir_okay=False)],
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        payload = runtime.classifications.import_file(source)
    except Exception as exc:
        payload = _operation_error("instruments.classifications.import", str(exc))
    _emit_json(payload)


@classifications_app.command("query")
def classifications_query(
    ctx: typer.Context,
    instrument: Annotated[str, typer.Option("--instrument")],
    as_of: Annotated[str, typer.Option("--as-of")],
    scheme: Annotated[str | None, typer.Option("--scheme")] = None,
    root: Annotated[Path | None, typer.Option(help="Override MARKET_DATA_DIR.")] = None,
) -> None:
    from app.services.market.history.catalog import instrument_payload, resolve_instrument

    runtime = market_runtime(ctx, root)
    settings = runtime.config
    settings.resolve_data_dir(root)
    try:
        matches = resolve_instrument(runtime.database, instrument)
        if len(matches) != 1:
            raise ValueError(f"instrument must resolve uniquely: {instrument}")
        memberships = runtime.classifications.memberships(
            matches[0].canonical_code,
            as_of=cast(date, _date_option(as_of, "as_of")),
            scheme_id=scheme,
        )
        payload = {
            "schema_version": "signal-lab.classification-query.v1",
            "status": "ok",
            "instrument": instrument_payload(matches[0]),
            "as_of": as_of,
            "memberships": memberships,
            "warnings": [],
        }
    except Exception as exc:
        payload = _operation_error("instruments.classifications.query", str(exc))
    _emit_json(payload)


@prices_app.command("compare")
def prices_compare(
    ctx: typer.Context,
    instruments: Annotated[list[str], typer.Option("--instrument", help="Repeat for every instrument.")],
    period: Annotated[str | None, typer.Option(help=PERIOD_HELP)] = None,
    start: Annotated[str | None, typer.Option()] = None,
    end: Annotated[str | None, typer.Option()] = None,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    cache_only: Annotated[bool, typer.Option("--cache-only")] = False,
    provider: Annotated[str | None, typer.Option()] = None,
    export: Annotated[str | None, typer.Option(help="csv or json.")] = None,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    try:
        if export not in {None, "csv", "json"}:
            raise ValueError("export must be csv or json")
        service, _, _ = _history_service(ctx, root)
        payload = service.compare(
            instruments, period=period, start=_date_option(start, "start"), end=_date_option(end, "end"),
            refresh=refresh, cache_only=cache_only, provider=provider, export=cast(Any, export),
        )
    except Exception as exc:
        payload = _command_error("prices.compare", str(exc))
    _emit_json(payload)


@prices_app.command("verify")
def prices_verify(
    ctx: typer.Context,
    instrument: Annotated[str, typer.Option("--instrument")],
    period: Annotated[str | None, typer.Option(help=PERIOD_HELP)] = None,
    start: Annotated[str | None, typer.Option()] = None,
    end: Annotated[str | None, typer.Option()] = None,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    cache_only: Annotated[bool, typer.Option("--cache-only")] = False,
    provider: Annotated[str | None, typer.Option()] = None,
    basis: Annotated[str | None, typer.Option(help="raw, adjusted or both.")] = None,
    export: Annotated[str | None, typer.Option(help="csv or json.")] = None,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:
    try:
        if basis not in {None, "raw", "adjusted", "both"}:
            raise ValueError("basis must be raw, adjusted or both")
        if export not in {None, "csv", "json"}:
            raise ValueError("export must be csv or json")
        service, _, _ = _history_service(ctx, root)
        payload = service.history(
            instrument, period=period, start=_date_option(start, "start"), end=_date_option(end, "end"),
            basis=cast(Any, basis), refresh=refresh, cache_only=cache_only,
            provider=provider, export=cast(Any, export),
        )
        payload["request"]["command"] = "prices.verify"
    except Exception as exc:
        payload = _command_error("prices.verify", str(exc))
    _emit_json(payload)


@macro_app.command("history")
def macro_history(
    ctx: typer.Context,
    series: Annotated[str, typer.Option("--series")],
    period: Annotated[str | None, typer.Option(help=PERIOD_HELP)] = None,
    start: Annotated[str | None, typer.Option()] = None,
    end: Annotated[str | None, typer.Option()] = None,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    cache_only: Annotated[bool, typer.Option("--cache-only")] = False,
    provider: Annotated[str, typer.Option()] = "fred",
    export: Annotated[str | None, typer.Option(help="csv or json.")] = None,
    root: Annotated[Path | None, typer.Option()] = None,
) -> None:

    try:
        if provider.casefold() != "fred":
            raise ValueError("macro history currently supports only the fred provider")
        if export not in {None, "csv", "json"}:
            raise ValueError("export must be csv or json")
        runtime = market_runtime(ctx, root)
        settings = runtime.config
        settings.resolve_data_dir(root)
        payload = runtime.macro.history(
            series, period=period, start=_date_option(start, "start"), end=_date_option(end, "end"),
            refresh=refresh, cache_only=cache_only, export=cast(Any, export),
        )
    except Exception as exc:
        payload = _command_error("macro.history", str(exc))
    _emit_json(payload)
