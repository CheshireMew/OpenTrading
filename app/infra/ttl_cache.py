from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

TKey = TypeVar("TKey", bound=Hashable)
TValue = TypeVar("TValue")


class TtlMemoryCache(Generic[TKey, TValue]):
    def __init__(self, ttl_seconds: float, *, copy_value: Callable[[TValue], TValue] | None = None) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self.copy_value = copy_value
        self._items: dict[TKey, tuple[float, TValue]] = {}

    def get(self, key: TKey) -> TValue | None:
        cached = self._items.get(key)
        if cached is None:
            return None
        expires_at, value = cached
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        return self.copy_value(value) if self.copy_value is not None else value

    def set(self, key: TKey, value: TValue) -> None:
        cached_value = self.copy_value(value) if self.copy_value is not None else value
        self._items[key] = (time.monotonic() + self.ttl_seconds, cached_value)

    def clear(self) -> None:
        self._items.clear()
