from __future__ import annotations

import json
from typing import Any

from app.infra.cache_memory import LocalTTLCache
from app.infra.executor import run_compute
from config import settings


def _serialize(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _deserialize(value: Any) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


class CacheService:
    """Process-local TTL cache bounded by entry count and serialized byte size."""

    def __init__(self, app_settings=settings) -> None:
        self.memory = LocalTTLCache(
            max_entries=app_settings.CACHE_MEMORY_MAX_ENTRIES,
            max_bytes=app_settings.CACHE_MEMORY_MAX_BYTES,
        )

    @property
    def local_entry_count(self) -> int:
        return self.memory.entry_count

    @property
    def local_byte_size(self) -> int:
        return self.memory.byte_size

    @property
    def runtime_backend(self) -> str:
        return "memory"

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        serialized = _serialize(value)
        return self.memory.set(key, serialized, ttl)

    def get(self, key: str) -> Any | None:
        value = self.memory.get(key)
        return _deserialize(value) if value is not None else None

    def delete(self, key: str) -> bool:
        return self.memory.delete(key)

    def delete_prefix(self, prefix: str) -> int:
        return self.memory.delete_prefix(prefix)

    async def aget(self, key: str) -> Any | None:
        value = self.memory.get(key)
        if value is None:
            return None
        # Small values are cheap; historical arrays must not monopolize the
        # API event loop. The stored string stays immutable across eviction.
        if len(value) < 16_384:
            return _deserialize(value)
        return await run_compute(lambda: _deserialize(value))

    async def aset(self, key: str, value: Any, ttl: int = 300) -> bool:
        return await run_compute(lambda: self.set(key, value, ttl))

    async def adelete(self, key: str) -> bool:
        return self.delete(key)

    async def adelete_prefix(self, prefix: str) -> int:
        return self.delete_prefix(prefix)


def build_cache_service(app_settings=settings) -> CacheService:
    return CacheService(app_settings)


__all__ = ["CacheService", "build_cache_service"]
