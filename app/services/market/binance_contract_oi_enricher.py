from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.infra.executor import run_database
from app.domain.market.math import percentage_change
from config import settings

from .binance_numbers import safe_float
from .ttl_cache import TtlMemoryCache

if TYPE_CHECKING:
    from .binance_usdm_market import BinanceUsdmMarketService


CONTRACT_OI_CACHE_TTL_SECONDS = 300.0
CONTRACT_OI_ENRICHMENT_TIMEOUT_SECONDS = 8.0
CONTRACT_OI_REQUEST_TIMEOUT_SECONDS = 2.5
CONTRACT_OI_CANDIDATE_LIMIT = settings.BINANCE_CONTRACT_OI_CANDIDATE_LIMIT


class BinanceContractOpenInterestEnricher:
    def __init__(self, usdm: BinanceUsdmMarketService) -> None:
        self.usdm = usdm
        self._cache: TtlMemoryCache[str, dict[str, float | None]] = TtlMemoryCache(
            CONTRACT_OI_CACHE_TTL_SECONDS,
            copy_value=dict,
        )

    async def load_changes(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
        symbols = self.candidate_symbols(rows)
        if not symbols:
            return {}

        async def load(symbol: str) -> tuple[str, dict[str, float | None]]:
            cached = self._cache.get(symbol)
            if cached is not None:
                return symbol, cached

            stored_response = await run_database(
                lambda: self.usdm.get_cached_open_interest_stats(symbol=symbol, period="1h", limit=25)
            )
            summary = self._summarize_open_interest_change(self._items(stored_response))
            if summary:
                self._cache.set(symbol, summary)
                return symbol, summary

            try:
                response = await asyncio.wait_for(
                    self.usdm.get_open_interest_stats(symbol=symbol, period="1h", limit=25),
                    timeout=CONTRACT_OI_REQUEST_TIMEOUT_SECONDS,
                )
                summary = self._summarize_open_interest_change(self._items(response))
            except Exception:
                summary = {}
            self._cache.set(symbol, summary)
            return symbol, summary

        semaphore = asyncio.Semaphore(8)

        async def guarded(symbol: str) -> tuple[str, dict[str, float | None]]:
            async with semaphore:
                return await load(symbol)

        tasks = [asyncio.create_task(guarded(symbol)) for symbol in symbols]
        done, pending = await asyncio.wait(tasks, timeout=CONTRACT_OI_ENRICHMENT_TIMEOUT_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        pairs: list[tuple[str, dict[str, float | None]]] = []
        for task in done:
            if task.cancelled():
                continue
            try:
                pairs.append(task.result())
            except Exception:
                continue
        return {symbol: summary for symbol, summary in pairs}

    def _items(self, payload: Any) -> list[dict[str, Any]]:
        data = payload.model_dump() if hasattr(payload, "model_dump") else payload
        return data.get("items", []) if isinstance(data, dict) else []

    def candidate_symbols(self, rows: list[dict[str, Any]]) -> list[str]:
        sorted_rows = sorted(
            rows,
            key=lambda item: safe_float(item.get("quote_volume")) or 0.0,
            reverse=True,
        )
        return [
            str(item.get("symbol") or "").upper()
            for item in sorted_rows[:CONTRACT_OI_CANDIDATE_LIMIT]
            if str(item.get("symbol") or "").upper().endswith("USDT")
        ]

    def _summarize_open_interest_change(self, items: list[dict[str, Any]]) -> dict[str, float | None]:
        ordered = [item for item in items if safe_float(item.get("sum_open_interest")) is not None]
        if not ordered:
            return {}
        latest = ordered[-1]
        return {
            "open_interest": safe_float(latest.get("sum_open_interest")),
            "open_interest_value": safe_float(latest.get("sum_open_interest_value")),
            "oi_change_1h_pct": self._change_pct(ordered, 1),
            "oi_change_4h_pct": self._change_pct(ordered, 4),
            "oi_change_24h_pct": self._change_pct(ordered, 24),
        }

    def _change_pct(self, items: list[dict[str, Any]], lookback: int) -> float | None:
        if len(items) <= lookback:
            return None
        current = safe_float(items[-1].get("sum_open_interest"))
        previous = safe_float(items[-1 - lookback].get("sum_open_interest"))
        if current is None or previous in (None, 0):
            return None
        return percentage_change(current, previous)
