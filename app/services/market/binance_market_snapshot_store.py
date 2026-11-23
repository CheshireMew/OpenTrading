from __future__ import annotations

import asyncio
import time
from typing import Any

from .binance_numbers import safe_float
from app.domain.market.quotes import MarketQuote
from config import settings


class BinanceMarketSnapshotStore:
    def __init__(self) -> None:
        self._spot_ticker: dict[str, dict[str, Any]] = {}
        self._usdm_ticker: dict[str, dict[str, Any]] = {}
        self._usdm_mark: dict[str, dict[str, Any]] = {}
        self._loaded_sources: set[str] = set()
        self._updated_at: dict[str, int] = {}
        self._quote_times: dict[tuple[str, str], tuple[int, int]] = {}
        self._lock = asyncio.Lock()

    async def market_page_snapshot(self) -> dict[str, Any]:
        return await self.market_page_snapshot_data()

    async def market_page_snapshot_data(self) -> dict[str, Any]:
        async with self._lock:
            load_errors: list[str] = []
            if not self.source_fresh("spot_ticker"):
                load_errors.append("现货榜单")
            if not self.source_fresh("usdm_ticker"):
                load_errors.append("U本位24H")
            if not self.source_fresh("usdm_mark"):
                load_errors.append("U本位Funding")
            return {
                "spot_ticker": self._ticker_payload("spot", self._fresh_rows("spot_ticker", self._spot_ticker)),
                "usdm_ticker": self._ticker_payload("usdm", self._fresh_rows("usdm_ticker", self._usdm_ticker)),
                "usdm_mark": self._mark_payload("usdm", self._fresh_rows("usdm_mark", self._usdm_mark)),
                "load_errors": load_errors,
                "updated_at": max(self._updated_at.values(), default=0),
            }

    async def has_snapshot(self) -> bool:
        async with self._lock:
            return bool(self._loaded_sources)

    async def has_market_page_snapshot(self) -> bool:
        async with self._lock:
            return {"spot_ticker", "usdm_ticker", "usdm_mark"}.issubset(self._loaded_sources)

    def source_fresh(self, source):
        return 0 <= int(time.time() * 1000) - self._updated_at.get(source, 0) <= settings.MARKET_STREAM_STALE_SECONDS * 1000

    def freshness(self):
        return {source: self.source_fresh(source) for source in ("spot_ticker", "usdm_ticker", "usdm_mark")}

    def _fresh_rows(self, source, rows):
        now = int(time.time() * 1000)
        return [row for symbol, row in rows.items() if -5_000 <= now - self._quote_times.get((source, symbol), (0, 0))[0]
                <= settings.MARKET_QUOTE_MAX_AGE_SECONDS * 1000]

    async def current_quote(self, symbol: str) -> MarketQuote:
        market = "usdm" if ":usdm:" in symbol or symbol.endswith(".P") else "spot"
        plain = symbol.split(":")[-1].removesuffix(".P")
        ticker_symbol = self._to_ticker_symbol(plain)
        async with self._lock:
            stale = MarketQuote(market=market)
            sources = [("spot_ticker", self._spot_ticker, "last_price")] if market == "spot" else [
                ("usdm_mark", self._usdm_mark, "mark_price"), ("usdm_ticker", self._usdm_ticker, "last_price")]
            for source, rows, price_field in sources:
                row = rows.get(ticker_symbol)
                if row is not None:
                    observed, received = self._quote_times.get((source, ticker_symbol), (0, 0))
                    quote = MarketQuote(safe_float(row.get(price_field)), observed, received, "websocket_snapshot", market)
                    if quote.fresh(int(time.time() * 1000), settings.MARKET_QUOTE_MAX_AGE_SECONDS):
                        return quote
                    # A stale mark must not hide a fresh ticker for that venue.
                    if quote.observed_at and (not stale.observed_at or quote.observed_at > stale.observed_at):
                        stale = quote
        return stale

    async def current_price(self, symbol: str) -> float | None:
        quote = await self.current_quote(symbol)
        return quote.value if quote.fresh(int(time.time() * 1000), settings.MARKET_QUOTE_MAX_AGE_SECONDS) else None

    def _record_time(self, source, symbol, row, now):
        observed = row.get("event_time") or row.get("time") or row.get("close_time") or now
        self._quote_times[(source, symbol)] = (int(observed), now)

    async def merge_tickers(self, source: str, rows: list[dict[str, Any]]) -> None:
        now = int(time.time() * 1000)
        target = self._spot_ticker if source == "spot_ticker" else self._usdm_ticker
        async with self._lock:
            for row in rows:
                symbol = str(row.get("symbol") or "").upper()
                if symbol:
                    observed = int(row.get("event_time") or row.get("time") or row.get("close_time") or now)
                    if observed >= self._quote_times.get((source, symbol), (0, 0))[0]:
                        target[symbol] = row
                        self._record_time(source, symbol, row, now)
            if rows:
                self._updated_at[source] = max((min(now, value[0]) for (venue, _), value in self._quote_times.items() if venue == source), default=0)
            else:
                self._updated_at[source] = now
            self._loaded_sources.add(source)

    async def merge_marks(self, rows: list[dict[str, Any]]) -> None:
        now = int(time.time() * 1000)
        async with self._lock:
            for row in rows:
                symbol = str(row.get("symbol") or "").upper()
                if symbol:
                    observed = int(row.get("time") or now)
                    if observed >= self._quote_times.get(("usdm_mark", symbol), (0, 0))[0]:
                        self._usdm_mark[symbol] = row
                        self._record_time("usdm_mark", symbol, row, now)
            if rows:
                self._updated_at["usdm_mark"] = max((min(now, value[0]) for (venue, _), value in self._quote_times.items() if venue == "usdm_mark"), default=0)
            else:
                self._updated_at["usdm_mark"] = now
            self._loaded_sources.add("usdm_mark")

    def ticker_response(self, market: str, rows: Any) -> dict[str, Any]:
        return self._ticker_payload(market, rows)

    def mark_response(self, market: str, rows: Any) -> dict[str, Any]:
        return self._mark_payload(market, rows)

    def _ticker_payload(self, market: str, rows: Any) -> dict[str, Any]:
        return {
            "exchange": "binance",
            "market": market,
            "items": sorted(list(rows), key=lambda item: item.get("quote_volume") or 0, reverse=True),
        }

    def _mark_payload(self, market: str, rows: Any) -> dict[str, Any]:
        return {
            "exchange": "binance",
            "market": market,
            "items": sorted(list(rows), key=lambda item: item.get("symbol") or ""),
        }

    def _to_ticker_symbol(self, symbol: str) -> str:
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return ""
        return normalized.replace("/", "")
