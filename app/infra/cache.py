"""Stable public cache API."""
from __future__ import annotations

from app.infra.cache_helpers import (
    optional_cache_aget,
    optional_cache_aset,
    optional_cache_get,
    optional_cache_set,
)
from app.infra.cache_service import CacheService, build_cache_service

__all__ = [
    "CacheService",
    "build_cache_service",
    "optional_cache_aget",
    "optional_cache_aset",
    "optional_cache_get",
    "optional_cache_set",
]
