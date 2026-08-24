from __future__ import annotations

from copy import deepcopy

from app.contracts.dto.market_insight import DliLiquidityResponse
from app.infra.cache import RedisService, optional_cache_get, optional_cache_set
from app.services.market.ttl_cache import TtlMemoryCache
from config import settings


DLI_LIQUIDITY_CACHE_PREFIX = "market:dli:liquidity:v3"


class DliLiquidityCache:
    def __init__(
        self,
        *,
        cache_service: RedisService | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self.cache_service = cache_service
        self.ttl_seconds = int(ttl_seconds or settings.DLI_CACHE_TTL)
        self.memory_cache: TtlMemoryCache[str, DliLiquidityResponse] = TtlMemoryCache(
            self.ttl_seconds,
            copy_value=deepcopy,
        )

    @staticmethod
    def key(days: int, change_days: int) -> str:
        return f"{DLI_LIQUIDITY_CACHE_PREFIX}:days:{days}:change_days:{change_days}"

    def get(self, *, days: int, change_days: int = 30) -> DliLiquidityResponse | None:
        cache_key = self.key(days, change_days)
        cached = self.memory_cache.get(cache_key)
        if cached is not None:
            return cached

        cached = optional_cache_get(self.cache_service, cache_key)
        if not isinstance(cached, dict):
            return None

        response = DliLiquidityResponse.model_validate(cached)
        self.memory_cache.set(cache_key, response)
        return deepcopy(response)

    def set(self, *, days: int, change_days: int = 30, payload: DliLiquidityResponse) -> None:
        cache_key = self.key(days, change_days)
        self.memory_cache.set(cache_key, payload)
        optional_cache_set(
            self.cache_service,
            cache_key,
            payload.model_dump(mode="json"),
            ttl=self.ttl_seconds,
            default_ttl=self.ttl_seconds,
        )

    def invalidate_all(self) -> None:
        self.memory_cache.clear()
        if self.cache_service is not None:
            self.cache_service.delete_prefix(DLI_LIQUIDITY_CACHE_PREFIX)
