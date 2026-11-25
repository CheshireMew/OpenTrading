"""One projection of Binance snapshots for alerts, screeners and research."""
from __future__ import annotations

import math
from typing import Any, Iterable

from app.domain.market.symbol_catalog import parse_market_symbol
from app.services.market.binance_numbers import safe_float


def _number(value: Any) -> float | None:
    parsed = safe_float(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def _identity(symbol: str) -> tuple[str, str | None]:
    value = symbol.strip().upper()
    if "/" in value or ":" in value:
        source = parse_market_symbol(value, default_exchange_id="binance")
        if source is not None:
            return source.symbol.split(":", 1)[0].replace("/", ""), (
                "usdm" if source.exchange_id == "binanceusdm" else "spot"
            )
    return value, None


class BinanceMarketObservations:
    """Join a single snapshot and optional extended page without losing market identity."""

    def __init__(self, snapshot: dict[str, Any], page=None) -> None:
        self.groups = {
            kind: {str(row["symbol"]).upper(): row for row in snapshot.get(kind, {}).get("items", []) if row.get("symbol")}
            for kind in ("spot_ticker", "usdm_ticker", "usdm_mark")
        }
        def record(row):
            return row if isinstance(row, dict) else row.model_dump(mode="json") if hasattr(row, "model_dump") else vars(row)
        self.page = page.model_dump(mode="json") if page is not None and hasattr(page, "model_dump") else {
            "monitor": {"items": [record(row) for row in page.monitor.items]},
            "contract_boards": {name: {"items": [record(row) for row in board.items]} for name, board in page.contract_boards.items()},
        } if page is not None else None
        self.scores = {(row.get("market", "spot"), row["symbol"].upper()): row
                       for row in self.page.get("monitor", {}).get("items", [])} if self.page is not None else {}
        self.oi = {row["symbol"].upper(): row.get("oi_change_1h_pct")
                   for board in self.page.get("contract_boards", {}).values() for row in board.get("items", []) if row.get("symbol")} if self.page is not None else {}

    def identity(self, symbol: str, market: str | None = None) -> tuple[str, str]:
        key, qualified_market = _identity(symbol)
        selected = market or qualified_market
        if selected is None:
            selected = "spot" if key in self.groups["spot_ticker"] else "usdm"
        return key, selected

    def metrics(self, symbol: str, market: str | None = None) -> dict[str, float | None]:
        key, selected = self.identity(symbol, market)
        ticker = self.groups[f"{selected}_ticker"].get(key, {})
        mark = self.groups["usdm_mark"].get(key, {})
        score = self.scores.get((selected, key))
        rate = _number(mark.get("funding_rate_pct"))
        if rate is None:
            raw = _number(mark.get("last_funding_rate"))
            rate = raw * 100 if raw is not None else None
        price = _number(ticker.get("last_price"))
        if price is None and selected == "usdm":
            price = _number(mark.get("mark_price"))
        natural = _number(score.get("natural_score")) if score is not None else None
        momentum = _number(score.get("momentum_score")) if score is not None else None
        return {
            "price": price,
            "price_change_24h": _number(ticker.get("price_change_pct")),
            "quote_volume": _number(ticker.get("quote_volume")),
            "funding_rate_pct": rate,
            "breakout_score": max(natural, momentum) if natural is not None and momentum is not None else None,
            "natural": natural, "momentum": momentum,
            "oi_change_1h_pct": _number(self.oi.get(key)),
        }

    def rows(self, market: str):
        for selected in ("spot", "usdm") if market == "all" else (market,):
            for symbol in self.groups[f"{selected}_ticker"]:
                yield selected, symbol, self.metrics(symbol, selected), self.scores.get((selected, symbol))

    def context(self, symbol: str) -> dict[str, Any]:
        key, selected = self.identity(symbol)
        result = {kind: rows[key] for kind, rows in self.groups.items() if key in rows}
        if self.page is not None:
            page = self.page
            score = next((row for row in page.get("monitor", {}).get("items", [])
                          if row.get("symbol") == key and row.get("market", "spot") == selected), None)
            if score is not None:
                result["breakoutMonitor"] = score
            result["marketBoardMemberships"] = [
                {"group": group, "board": name, "data": row}
                for group in ("spot_boards", "contract_boards")
                for name, board in page.get(group, {}).items()
                for row in board.get("items", []) if row.get("symbol") == key
            ]
        return result


class BinanceMarketObservationService:
    def __init__(self, snapshots, pages) -> None:
        self._snapshots, self._pages = snapshots, pages

    async def get_many(self, symbols: Iterable[str], *, extended: bool = False) -> dict[str, dict[str, float | None]]:
        snapshot = await self._snapshots.get_market_page_snapshot_data()
        page = await self._pages.get_page(min_rise_pct=0, limit=100, quote_asset="USDT") if extended else None
        observations = BinanceMarketObservations(snapshot, page)
        return {symbol: {key: value for key, value in observations.metrics(symbol).items() if key != "quote_volume"}
                for symbol in symbols}
