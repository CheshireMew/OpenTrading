"""Auditable scheduled operations with lazy public exports."""

from importlib import import_module
from typing import Any

__all__ = [
    "LIQUIDITY_REFRESH_JOB",
    "JobDefinition",
    "JobPreset",
    "JobRun",
    "JobScheduler",
    "JobWatcher",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    value = getattr(import_module("signal_lab.operations.scheduler"), name)
    globals()[name] = value
    return value
