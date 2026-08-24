from __future__ import annotations

import asyncio
from typing import Any

from app.infra.cache_service import RedisService


def optional_cache_get(cache_service: RedisService | None, key: str) -> Any | None:
    return None if cache_service is None else cache_service.get(key)


def optional_cache_set(
    cache_service: RedisService | None,
    key: str,
    value: Any,
    *,
    ttl: int | None,
    default_ttl: int,
) -> None:
    if cache_service is not None:
        cache_service.set(key, value, ttl=ttl or default_ttl)


async def optional_cache_aget(cache_service: RedisService | None, key: str) -> Any | None:
    if cache_service is None:
        return None
    async_get = getattr(cache_service, "aget", None)
    if async_get is not None:
        return await async_get(key)
    return await asyncio.to_thread(cache_service.get, key)


async def optional_cache_aset(
    cache_service: RedisService | None,
    key: str,
    value: Any,
    *,
    ttl: int | None,
    default_ttl: int,
) -> None:
    if cache_service is None:
        return
    resolved_ttl = ttl or default_ttl
    async_set = getattr(cache_service, "aset", None)
    if async_set is not None:
        await async_set(key, value, ttl=resolved_ttl)
        return
    await asyncio.to_thread(cache_service.set, key, value, ttl=resolved_ttl)


__all__ = [
    "optional_cache_aget",
    "optional_cache_aset",
    "optional_cache_get",
    "optional_cache_set",
]
