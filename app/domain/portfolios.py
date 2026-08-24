from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PortfolioCollectionRecord:
    revision: int
    active_portfolio_id: str
    active_payloads: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PortfolioDeletedSummaryRecord:
    portfolio_id: str
    name: str
    deleted_at: datetime


@dataclass(frozen=True, slots=True)
class PortfolioDeletedPageRecord:
    items: list[PortfolioDeletedSummaryRecord]
    offset: int
    limit: int
    total: int


@dataclass(frozen=True, slots=True)
class PortfolioSimulationResultRecord:
    portfolio_id: str
    result_payload: dict[str, Any] | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class PortfolioExportRecord:
    revision: int
    active_portfolio_id: str
    active_payloads: list[dict[str, Any]]
    deleted_payloads: list[dict[str, Any]]
    simulation_payloads: list[tuple[str, dict[str, Any]]]


def portfolio_simulation_fingerprint(payload: dict[str, Any]) -> str:
    simulation_input = {
        "assets": [
            {
                "symbol": asset.get("symbol", ""),
                "targetWeight": asset.get("targetWeight", 0),
            }
            for asset in payload.get("assets", [])
        ],
        "strategy": payload.get("strategy", {}),
        "simulation": payload.get("simulation", {}),
    }
    canonical = json.dumps(
        simulation_input,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PortfolioRevisionConflictError(Exception):
    """The caller based a write on an obsolete collection revision."""


class PortfolioNotFoundError(Exception):
    """The requested portfolio is not available in the requested collection state."""


class PortfolioCollectionMismatchError(Exception):
    """A change set does not describe a complete, internally consistent collection."""
