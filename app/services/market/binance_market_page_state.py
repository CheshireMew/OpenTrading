from __future__ import annotations

import asyncio
import time
from collections import OrderedDict

from app.contracts.dto.binance.page import BinanceMarketPageRefreshStatusResponse, BinanceMarketPageResponse
from config import settings

from .binance_breakout_candidates import normalize_quote_asset


PageKey = tuple[float, int, str]
DEFAULT_PAGE_CONFIGS = ((5.0, 24, "USDT"),)


class BinanceMarketPageState:
    def __init__(self) -> None:
        self._responses: OrderedDict[PageKey, BinanceMarketPageResponse] = OrderedDict()
        self._requested: set[PageKey] = {
            self.key(min_rise_pct=min_rise_pct, limit=limit, quote_asset=quote_asset)
            for min_rise_pct, limit, quote_asset in DEFAULT_PAGE_CONFIGS
        }
        now = time.monotonic()
        self._last_requested_at: OrderedDict[PageKey, float] = OrderedDict(
            (key, now) for key in self._requested
        )
        self._default_keys = set(self._requested)
        self._max_configs = max(int(settings.BINANCE_MARKET_PAGE_MAX_CONFIGS), 1)
        self._config_ttl = max(float(settings.BINANCE_MARKET_PAGE_CONFIG_TTL), 1.0)
        self._lock = asyncio.Lock()
        self._refreshing = 0
        self._last_started_at: int | None = None
        self._last_completed_at: int | None = None
        self._last_error: str | None = None

    @staticmethod
    def key(*, min_rise_pct: float, limit: int, quote_asset: str) -> PageKey:
        return (float(min_rise_pct), int(limit), normalize_quote_asset(quote_asset))

    async def register_request(self, key: PageKey) -> tuple[BinanceMarketPageResponse | None, bool]:
        async with self._lock:
            self._prune_locked()
            added = key not in self._requested
            self._requested.add(key)
            self._last_requested_at[key] = time.monotonic()
            self._last_requested_at.move_to_end(key)
            self._enforce_limit_locked(preserve=key)
            cached = self._responses.get(key)
            if cached is not None:
                self._responses.move_to_end(key)
            return (self.with_live_status(cached) if cached is not None else None, added)

    async def requested_keys(self) -> list[PageKey]:
        async with self._lock:
            self._prune_locked()
            return sorted(self._requested)

    async def store(self, key: PageKey, response: BinanceMarketPageResponse) -> None:
        async with self._lock:
            self._responses[key] = response
            self._responses.move_to_end(key)
            self._enforce_limit_locked(preserve=key)

    def _prune_locked(self) -> None:
        cutoff = time.monotonic() - self._config_ttl
        expired = [
            key
            for key, requested_at in self._last_requested_at.items()
            if key not in self._default_keys and requested_at < cutoff
        ]
        for key in expired:
            self._remove_locked(key)

    def _enforce_limit_locked(self, *, preserve: PageKey) -> None:
        while len(self._requested) > self._max_configs:
            evict = next(
                (
                    key
                    for key in self._last_requested_at
                    if key != preserve and key not in self._default_keys
                ),
                None,
            )
            if evict is None:
                evict = next(
                    (key for key in self._last_requested_at if key != preserve),
                    None,
                )
            if evict is None:
                break
            self._remove_locked(evict)

    def _remove_locked(self, key: PageKey) -> None:
        self._requested.discard(key)
        self._last_requested_at.pop(key, None)
        self._responses.pop(key, None)

    async def mark_started(self) -> None:
        async with self._lock:
            self._refreshing += 1
            self._last_started_at = int(time.time() * 1000)
            self._last_error = None

    async def mark_completed(self) -> None:
        async with self._lock:
            self._refreshing = max(0, self._refreshing - 1)
            self._last_completed_at = int(time.time() * 1000)

    async def mark_failed(self, error: Exception) -> None:
        async with self._lock:
            self._last_error = str(error)

    def build_status(
        self,
        *,
        snapshot_ready: bool,
        boards_ready: bool,
        monitor_ready: bool,
        oi_ready_count: int,
        oi_requested_count: int,
    ) -> BinanceMarketPageRefreshStatusResponse:
        return BinanceMarketPageRefreshStatusResponse(
            snapshot_ready=snapshot_ready,
            boards_ready=boards_ready,
            monitor_ready=monitor_ready,
            refreshing=self._refreshing > 0,
            oi_ready_count=oi_ready_count,
            oi_requested_count=oi_requested_count,
            last_refresh_started_at=self._last_started_at,
            last_refresh_completed_at=self._last_completed_at,
            last_refresh_error=self._last_error,
        )

    def with_live_status(self, response: BinanceMarketPageResponse) -> BinanceMarketPageResponse:
        status = response.refresh_status.model_copy(update={
            "refreshing": self._refreshing > 0,
            "last_refresh_started_at": self._last_started_at,
            "last_refresh_completed_at": self._last_completed_at,
            "last_refresh_error": self._last_error,
        })
        return response.model_copy(update={"refresh_status": status})
