from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class CachedPriceProjection:
    frame: pd.DataFrame
    records: tuple[dict[str, Any], ...]
    status: str
    instrument: dict[str, Any]
    coverage: dict[str, Any]
    source: dict[str, Any]
    price_basis: str
    artifact: dict[str, Any]
    warnings: tuple[str, ...]


class ProjectionCache:
    """Bounded cache that coalesces equal misses without serializing different keys."""

    def __init__(self, max_entries: int = 4) -> None:
        self._condition = Condition()
        self._entries: OrderedDict[tuple[Any, ...], CachedPriceProjection] = OrderedDict()
        self._inflight: set[tuple[Any, ...]] = set()
        self._max_entries = max_entries

    def get_or_create(
        self,
        key: tuple[Any, ...],
        factory: Callable[[], CachedPriceProjection],
    ) -> CachedPriceProjection:
        while True:
            with self._condition:
                cached = self._entries.get(key)
                if cached is not None:
                    self._entries.move_to_end(key)
                    return cached
                if key not in self._inflight:
                    self._inflight.add(key)
                    break
                self._condition.wait()
        try:
            created = factory()
        except BaseException:
            with self._condition:
                self._inflight.discard(key)
                self._condition.notify_all()
            raise
        with self._condition:
            self._entries[key] = created
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            self._inflight.discard(key)
            self._condition.notify_all()
        return created
