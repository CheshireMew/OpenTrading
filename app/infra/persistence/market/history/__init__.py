"""Canonical storage boundary with heavy writers loaded only when requested."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from app.infra.persistence.market.history.database import MarketHistoryDatabase

if TYPE_CHECKING:
    from app.infra.persistence.market.history.artifacts import artifact_json, artifact_records

__all__ = [
    "MarketHistoryDatabase",
    "artifact_json",
    "artifact_records",
]

_EXPORTS = {
    "artifact_json": ("app.infra.persistence.market.history.artifacts", "artifact_json"),
    "artifact_records": ("app.infra.persistence.market.history.artifacts", "artifact_records"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
