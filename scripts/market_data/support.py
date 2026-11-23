from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from config.market_data import MarketDataConfig
from app.contracts.market_data import history_envelope
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.price_repository import PriceRepository
from app.infra.structured_data import dumps_json

if TYPE_CHECKING:
    from app.services.market.history.prices import PriceService


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def history_service(root: Path | None) -> tuple[PriceService, Path, MarketDataConfig]:
    from app.services.market.history.prices import PriceService

    settings = MarketDataConfig.load()
    base = settings.resolve_data_dir(root)
    return PriceService(base, settings), base, settings


def date_option(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


def emit_json(payload: dict[str, Any]) -> None:
    typer.echo(dumps_json(payload, compact=True))
    if payload.get("status") == "error":
        raise typer.Exit(code=1)


def command_error(command: str, message: str) -> dict[str, Any]:
    return history_envelope("error", {"command": command}, warnings=[message])


def operation_error(command: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "signal-lab.operation.v1",
        "status": "error",
        "request": {"command": command},
        "warnings": [message],
    }


def dataset_instrument_selection(
    database: MarketHistoryDatabase,
    inline: list[str] | None,
    selection_file: Path | None,
    all_cached: bool,
) -> list[str]:
    from app.infra.persistence.market.history.contracts import load_json_document, require_object

    modes = int(bool(inline)) + int(selection_file is not None) + int(all_cached)
    if modes != 1:
        raise ValueError(
            "select instruments with exactly one of --instrument, --instruments-file or --all-cached"
        )
    if selection_file is not None:
        payload = require_object(
            load_json_document(selection_file),
            source="dataset instrument selection",
            required={"schema_version", "instruments"},
        )
        if payload["schema_version"] != "signal-lab.instrument-selection.v1":
            raise ValueError(
                f"unsupported instrument selection schema: {payload['schema_version']}"
            )
        if not isinstance(payload["instruments"], list):
            raise ValueError("dataset instrument selection must contain an instruments array")
        selected = payload["instruments"]
    elif all_cached:
        selected = [item["symbol"] for item in PriceRepository(database).price_inventory()]
    else:
        selected = inline or []
    if not selected or any(not isinstance(item, str) or not item.strip() for item in selected):
        raise ValueError("dataset instrument selection requires non-empty instrument strings")
    return list(dict.fromkeys(item.strip() for item in selected))
