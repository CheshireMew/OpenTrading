from __future__ import annotations

import threading
import time
from collections import OrderedDict
from sys import getsizeof
from typing import Any


class LocalTTLCache:
    def __init__(self, *, max_entries: int, max_bytes: int | None = None) -> None:
        self.max_entries = max(int(max_entries), 1)
        self.max_bytes = max(int(max_bytes), 1) if max_bytes is not None else None
        self._entries: OrderedDict[str, tuple[float, Any, int]] = OrderedDict()
        self._byte_size = 0
        self._lock = threading.RLock()

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def byte_size(self) -> int:
        with self._lock:
            return self._byte_size

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value, _weight = entry
            if expires_at <= now:
                self._remove(key)
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: int) -> bool:
        expires_at = time.monotonic() + max(int(ttl), 1)
        weight = self._weight(key, value)
        with self._lock:
            self._remove_expired(time.monotonic())
            self._remove(key)
            if self.max_bytes is not None and weight > self.max_bytes:
                return False
            self._entries[key] = (expires_at, value, weight)
            self._byte_size += weight
            self._entries.move_to_end(key)
            while (
                len(self._entries) > self.max_entries
                or (self.max_bytes is not None and self._byte_size > self.max_bytes)
            ):
                oldest_key = next(iter(self._entries))
                self._remove(oldest_key)
            return key in self._entries

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._remove(key)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]
            for key in keys:
                self._remove(key)
            return len(keys)

    def _remove_expired(self, now: float) -> None:
        expired = [key for key, (expires_at, _value, _weight) in self._entries.items() if expires_at <= now]
        for key in expired:
            self._remove(key)

    def _remove(self, key: str) -> bool:
        entry = self._entries.pop(key, None)
        if entry is None:
            return False
        self._byte_size -= entry[2]
        return True

    @staticmethod
    def _weight(key: str, value: Any) -> int:
        key_size = len(key.encode("utf-8"))
        if isinstance(value, str):
            return key_size + len(value.encode("utf-8"))
        if isinstance(value, (bytes, bytearray, memoryview)):
            return key_size + len(value)
        return key_size + getsizeof(value)


__all__ = ["LocalTTLCache"]
