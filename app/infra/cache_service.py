from __future__ import annotations

import json
from typing import Any

from app.infra.cache_memory import LocalTTLCache
from app.infra.redis_connections import RedisConnections
from config import settings
from utils.logger import logger


def _serialize(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _deserialize(value: Any) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


class RedisService:
    """Two-level cache facade: bounded local TTL cache with optional Redis backing."""

    def __init__(self, app_settings=settings) -> None:
        self.settings = app_settings
        self.memory = LocalTTLCache(
            max_entries=app_settings.CACHE_MEMORY_MAX_ENTRIES,
            max_bytes=app_settings.CACHE_MEMORY_MAX_BYTES,
        )
        self.connections = RedisConnections(app_settings)

    @property
    def local_entry_count(self) -> int:
        return self.memory.entry_count

    @property
    def local_byte_size(self) -> int:
        return self.memory.byte_size

    @property
    def runtime_backend(self) -> str:
        return "redis" if (self.connections.client is not None or self.connections.async_client is not None) else "memory_fallback"

    def connect(self, *, force: bool = False) -> None:
        self.connections.connect(force=force)

    async def connect_async(self, *, force: bool = False) -> None:
        await self.connections.connect_async(force=force)

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        serialized = _serialize(value)
        self.memory.set(key, serialized, ttl)
        if not self.connections.ensure_sync():
            return True
        try:
            return bool(self.connections.client.setex(key, ttl, serialized))
        except Exception as exc:
            logger.warning(f"Redis Set Error: {exc}")
            self.connections.discard_sync()
            return False

    def get(self, key: str) -> Any | None:
        local_value = self.memory.get(key)
        if local_value is not None:
            return _deserialize(local_value)
        if not self.connections.ensure_sync():
            return None
        try:
            value = self.connections.client.get(key)
            if not value:
                return None
            parsed = _deserialize(value)
            self.memory.set(key, _serialize(parsed), self.settings.CACHE_MEMORY_DEFAULT_TTL)
            return parsed
        except Exception as exc:
            logger.warning(f"Redis Get Error: {exc}")
            self.connections.discard_sync()
            return None

    def delete(self, key: str) -> bool:
        local_deleted = self.memory.delete(key)
        if not self.connections.ensure_sync():
            return local_deleted
        try:
            return bool(self.connections.client.delete(key)) or local_deleted
        except Exception as exc:
            logger.warning(f"Redis Delete Error: {exc}")
            self.connections.discard_sync()
            return False

    def delete_prefix(self, prefix: str) -> int:
        local_count = self.memory.delete_prefix(prefix)
        if not self.connections.ensure_sync():
            return local_count
        try:
            keys = list(self.connections.client.scan_iter(f"{prefix}*"))
            if not keys:
                return local_count
            return max(int(self.connections.client.delete(*keys)), local_count)
        except Exception as exc:
            logger.warning(f"Redis Delete Prefix Error: {exc}")
            self.connections.discard_sync()
            return local_count

    async def aget(self, key: str) -> Any | None:
        local_value = self.memory.get(key)
        if local_value is not None:
            return _deserialize(local_value)
        if not await self.connections.ensure_async():
            return None
        try:
            value = await self.connections.async_client.get(key)
            if not value:
                return None
            parsed = _deserialize(value)
            self.memory.set(key, _serialize(parsed), self.settings.CACHE_MEMORY_DEFAULT_TTL)
            return parsed
        except Exception as exc:
            logger.warning(f"Redis Async Get Error: {exc}")
            await self.connections.discard_async()
            return None

    async def aset(self, key: str, value: Any, ttl: int = 300) -> bool:
        serialized = _serialize(value)
        self.memory.set(key, serialized, ttl)
        if not await self.connections.ensure_async():
            return True
        try:
            await self.connections.async_client.setex(key, ttl, serialized)
            return True
        except Exception as exc:
            logger.warning(f"Redis Async Set Error: {exc}")
            await self.connections.discard_async()
            return True

    async def adelete(self, key: str) -> bool:
        local_deleted = self.memory.delete(key)
        if not await self.connections.ensure_async():
            return local_deleted
        try:
            return bool(await self.connections.async_client.delete(key)) or local_deleted
        except Exception as exc:
            logger.warning(f"Redis Async Delete Error: {exc}")
            await self.connections.discard_async()
            return local_deleted

    async def adelete_prefix(self, prefix: str) -> int:
        local_count = self.memory.delete_prefix(prefix)
        if not await self.connections.ensure_async():
            return local_count
        try:
            keys = [key async for key in self.connections.async_client.scan_iter(f"{prefix}*")]
            if not keys:
                return local_count
            return max(int(await self.connections.async_client.delete(*keys)), local_count)
        except Exception as exc:
            logger.warning(f"Redis Async Delete Prefix Error: {exc}")
            await self.connections.discard_async()
            return local_count

    async def aclose(self) -> None:
        await self.connections.close()


def build_cache_service(app_settings=settings) -> RedisService:
    return RedisService(app_settings)


__all__ = ["RedisService", "build_cache_service"]
