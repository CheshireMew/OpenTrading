"""Canonical storage boundary with heavy writers loaded only when requested."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from signal_lab.storage.database import SignalLabDatabase

if TYPE_CHECKING:
    from signal_lab.storage.artifacts import artifact_json, artifact_records
    from signal_lab.storage.market import MarketDataStore

__all__ = [
    "MarketDataStore",
    "SignalLabDatabase",
    "artifact_json",
    "artifact_records",
]

_EXPORTS = {
    "MarketDataStore": ("signal_lab.storage.market", "MarketDataStore"),
    "artifact_json": ("signal_lab.storage.artifacts", "artifact_json"),
    "artifact_records": ("signal_lab.storage.artifacts", "artifact_records"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
