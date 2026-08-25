from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.application.persistence_ports import MarketScreenerRepositoryPort
from app.contracts.research import (
    MarketScreenerRunCommand,
    MarketScreenerRunPageResponse,
    MarketScreenerRunResponse,
    ResearchArchiveCommand,
    SavedMarketScreenerCreateCommand,
    SavedMarketScreenerListResponse,
    SavedMarketScreenerResponse,
    SavedMarketScreenerUpdateCommand,
)
from app.infra.executor import run_database


class MarketScreenerService:
    def __init__(
        self,
        *,
        repository: MarketScreenerRepositoryPort,
        binance_market_service,
        market_query_service=None,
        binance_web3_heat_rank_service=None,
    ) -> None:
        self._repository = repository
        self._binance = binance_market_service
        self._market_query = market_query_service
        self._web3_heat_ranks = binance_web3_heat_rank_service

    def list_screeners(self, *, include_archived: bool) -> SavedMarketScreenerListResponse:
        return SavedMarketScreenerListResponse(items=self._repository.list_screeners(include_archived=include_archived))

    def create(self, command: SavedMarketScreenerCreateCommand) -> SavedMarketScreenerResponse:
        return SavedMarketScreenerResponse.model_validate(self._repository.create_screener(self._payload(command)))

    def update(self, screener_id: str, command: SavedMarketScreenerUpdateCommand) -> SavedMarketScreenerResponse:
        return SavedMarketScreenerResponse.model_validate(
            self._repository.update_screener(screener_id, command.expectedVersion, self._payload(command))
        )

    def archive(
        self, screener_id: str, command: ResearchArchiveCommand, *, archived: bool
    ) -> SavedMarketScreenerResponse:
        return SavedMarketScreenerResponse.model_validate(
            self._repository.set_screener_archived(screener_id, command.expectedVersion, archived)
        )

    def list_runs(self, screener_id: str, *, offset: int, limit: int) -> MarketScreenerRunPageResponse:
        rows, total = self._repository.list_runs(screener_id, offset=offset, limit=limit)
        return MarketScreenerRunPageResponse(items=rows, total=total)

    async def run(self, screener_id: str, command: MarketScreenerRunCommand) -> MarketScreenerRunResponse:
        if command.asOf is not None:
            as_of = command.asOf.astimezone(timezone.utc).replace(tzinfo=None) if command.asOf.tzinfo else command.asOf
            return MarketScreenerRunResponse.model_validate(
                await run_database(lambda: self._repository.get_run_as_of(screener_id, as_of))
            )
        screener = await run_database(lambda: self._repository.get_screener(screener_id))
        filters = screener["filters"]
        snapshot = await self._binance.snapshot_service.get_market_page_snapshot_data()
        page = await self._binance.page.get_page(
            min_rise_pct=0, limit=100, quote_asset=filters.get("quoteAsset", "USDT")
        )
        exchange_items = self._filter(snapshot, page, {**filters, "limit": 500})
        exchange_items = await self._apply_rsi_filters(exchange_items, filters)
        web3_items = await self._load_web3_items(filters)
        items = sorted(
            [*exchange_items, *web3_items],
            key=lambda item: (
                item.get("breakoutScore") if item.get("breakoutScore") is not None else -1,
                item.get("heatScore") if item.get("heatScore") is not None else -1,
                item.get("priceChangePct") if item.get("priceChangePct") is not None else -999,
                item.get("quoteVolume") or 0,
            ),
            reverse=True,
        )[: int(filters.get("limit") or 100)]
        evaluated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        updated_ms = max(int(snapshot.get("updated_at") or 0), int(page.updated_at or 0))
        snapshot_as_of = (
            datetime.fromtimestamp(updated_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
            if updated_ms
            else evaluated_at
        )
        row = await run_database(
            lambda: self._repository.save_run(
                screener_id,
                {
                    "filters_snapshot": filters,
                    "result_items": items,
                    "result_count": len(items),
                    "snapshot_as_of": snapshot_as_of,
                    "evaluated_at": evaluated_at,
                },
            )
        )
        return MarketScreenerRunResponse.model_validate(row)

    async def _apply_rsi_filters(
        self,
        items: list[dict[str, Any]],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        minimum = filters.get("minRsi")
        maximum = filters.get("maxRsi")
        if minimum is None and maximum is None:
            return items
        if self._market_query is None:
            return []
        semaphore = asyncio.Semaphore(8)

        async def enrich(item: dict[str, Any]) -> dict[str, Any] | None:
            async with semaphore:
                symbol = str(item["symbol"])
                quote = str(filters.get("quoteAsset") or "USDT").upper()
                normalized = f"{symbol[:-len(quote)]}/{quote}" if symbol.endswith(quote) else symbol
                try:
                    response = await self._market_query.get_realtime(symbol=normalized, timeframe="1h", limit=200)
                    rsi = self._number(response.indicators.rsi if response.indicators else None)
                except Exception:
                    return None
                if minimum is not None and (rsi is None or rsi < minimum):
                    return None
                if maximum is not None and (rsi is None or rsi > maximum):
                    return None
                return {**item, "rsi": rsi}

        return [row for row in await asyncio.gather(*(enrich(item) for item in items)) if row is not None]

    async def _load_web3_items(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        if not filters.get("includeWeb3") or self._web3_heat_ranks is None:
            return []
        response = await self._web3_heat_ranks.get_web3_heat_rank_boards(
            chain_id=filters.get("web3ChainId"),
            size=min(100, max(30, int(filters.get("limit") or 100))),
        )
        board = response.boards.get("heat_score_desc")
        allow = {str(value).upper() for value in filters.get("symbols") or []}
        result: list[dict[str, Any]] = []
        for item in board.items if board else []:
            metrics = item.metrics
            symbol = str(item.symbol or "").upper()
            address = str(item.contract_address or "")
            if allow and symbol not in allow and address.upper() not in allow:
                continue
            change = self._number(metrics.percent_change_24h)
            volume = self._number(metrics.volume_24h)
            risk = self._number(metrics.smart_money_risk_level)
            if filters.get("minPriceChangePct") is not None and (
                change is None or change < filters["minPriceChangePct"]
            ):
                continue
            if filters.get("maxPriceChangePct") is not None and (
                change is None or change > filters["maxPriceChangePct"]
            ):
                continue
            if filters.get("minQuoteVolume") is not None and (
                volume is None or volume < filters["minQuoteVolume"]
            ):
                continue
            if filters.get("maxWeb3RiskLevel") is not None and (
                risk is None or risk > filters["maxWeb3RiskLevel"]
            ):
                continue
            if any(
                filters.get(key) is not None
                for key in (
                    "maxFundingRatePct",
                    "minBreakoutScore",
                    "minOiChange1hPct",
                    "minRsi",
                    "maxRsi",
                )
            ):
                continue
            result.append({
                "market": "web3",
                "assetClass": "web3",
                "symbol": symbol or address,
                "chainId": item.chain_id,
                "platform": item.platform,
                "contractAddress": address,
                "lastPrice": self._number(metrics.price),
                "priceChangePct": change,
                "quoteVolume": volume,
                "heatScore": item.heat_score,
                "web3RiskLevel": int(risk) if risk is not None else None,
                "rank": item.rank,
            })
        return result

    @staticmethod
    def _payload(command: SavedMarketScreenerCreateCommand) -> dict[str, Any]:
        return {
            "name": command.name.strip(),
            "description": command.description.strip(),
            "filters": command.filters.model_dump(),
        }

    @classmethod
    def _filter(cls, snapshot: dict[str, Any], page, filters: dict[str, Any]) -> list[dict[str, Any]]:
        market = filters.get("market", "all")
        rows = []
        if market in {"spot", "all"}:
            rows.extend(("spot", item) for item in snapshot.get("spot_ticker", {}).get("items", []))
        if market in {"usdm", "all"}:
            rows.extend(("usdm", item) for item in snapshot.get("usdm_ticker", {}).get("items", []))
        marks = {str(item.get("symbol") or "").upper(): item for item in snapshot.get("usdm_mark", {}).get("items", [])}
        scores = {(item.market, item.symbol): item for item in page.monitor.items}
        oi = {}
        for board in page.contract_boards.values():
            for item in board.items:
                if item.symbol:
                    oi[item.symbol.upper()] = item
        quote = str(filters.get("quoteAsset") or "USDT").upper()
        allow = set(filters.get("symbols") or [])
        result = []
        for source, raw in rows:
            symbol = str(raw.get("symbol") or "").upper()
            if not symbol.endswith(quote) or (allow and symbol not in allow):
                continue
            change = cls._number(raw.get("price_change_pct"))
            volume = cls._number(raw.get("quote_volume"))
            mark = marks.get(symbol, {})
            funding = cls._number(mark.get("funding_rate_pct"))
            if funding is None:
                base = cls._number(mark.get("last_funding_rate"))
                funding = base * 100 if base is not None else None
            score_item = scores.get((source, symbol))
            breakout = max(score_item.natural_score, score_item.momentum_score) if score_item else None
            oi_change = cls._number(getattr(oi.get(symbol), "oi_change_1h_pct", None))
            if filters.get("minPriceChangePct") is not None and (
                change is None or change < filters["minPriceChangePct"]
            ):
                continue
            if filters.get("maxPriceChangePct") is not None and (
                change is None or change > filters["maxPriceChangePct"]
            ):
                continue
            if filters.get("minQuoteVolume") is not None and (volume is None or volume < filters["minQuoteVolume"]):
                continue
            if (
                source == "usdm"
                and filters.get("maxFundingRatePct") is not None
                and (funding is None or funding > filters["maxFundingRatePct"])
            ):
                continue
            if filters.get("minBreakoutScore") is not None and (
                breakout is None or breakout < filters["minBreakoutScore"]
            ):
                continue
            if filters.get("minOiChange1hPct") is not None and (
                oi_change is None or oi_change < filters["minOiChange1hPct"]
            ):
                continue
            result.append(
                {
                    "market": source,
                    "symbol": symbol,
                    "lastPrice": cls._number(raw.get("last_price")),
                    "priceChangePct": change,
                    "quoteVolume": volume,
                    "fundingRatePct": funding,
                    "breakoutScore": breakout,
                    "oiChange1hPct": oi_change,
                    "verdict": score_item.verdict if score_item else None,
                }
            )
        result.sort(
            key=lambda item: (
                item.get("breakoutScore") or -1,
                item.get("priceChangePct") or -999,
                item.get("quoteVolume") or 0,
            ),
            reverse=True,
        )
        return result[: int(filters.get("limit") or 100)]

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
