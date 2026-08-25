from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.application.errors import InvalidRequestError
from app.application.persistence_ports import ResearchRepositoryPort, TradeSignalRepositoryPort
from app.contracts.research import AssetResearchResponse
from app.domain.market.constants import timeframe_to_milliseconds
from app.infra.executor import run_database, run_tool
from app.services.market.symbol_catalog import resolve_market_asset


class AssetResearchService:
    def __init__(
        self,
        *,
        research_repository: ResearchRepositoryPort,
        signal_repository: TradeSignalRepositoryPort,
        market_query_service,
        index_data_service,
        binance_market_service,
        binance_web3_heat_rank_service,
        binance_web3_token_service,
        pair_compare_service,
    ) -> None:
        self._research = research_repository
        self._signals = signal_repository
        self._market_query = market_query_service
        self._indexes = index_data_service
        self._binance = binance_market_service
        self._web3_heat_ranks = binance_web3_heat_rank_service
        self._web3_tokens = binance_web3_token_service
        self._pair_compare = pair_compare_service

    async def get_asset(
        self,
        *,
        symbol: str,
        timeframe: str,
        history_days: int,
        asset_class: str | None = None,
        chain_id: str | None = None,
        platform: str | None = None,
    ) -> AssetResearchResponse:
        workbench = await run_database(lambda: self._research.get_workbench(event_limit=500, note_limit=1_000))
        web3_item = next(
            (
                item for item in workbench["items"]
                if item["assetClass"] == "web3" and item["symbol"].casefold() == symbol.casefold()
            ),
            None,
        )
        if web3_item is None and asset_class == "web3":
            web3_item = {
                "id": "",
                "symbol": symbol,
                "assetClass": "web3",
                "sourceContext": {
                    "chainId": chain_id,
                    "platform": platform,
                    "contractAddress": symbol,
                },
            }
        resolved = resolve_market_asset(symbol) if web3_item is None else None
        if resolved is None and web3_item is None:
            raise InvalidRequestError("该标的不在统一市场目录中，也不在当前研究清单中")
        normalized = web3_item["symbol"] if web3_item else resolved["symbol"]
        asset_class = "web3" if web3_item else resolved["asset_class"]
        now = datetime.now(timezone.utc)
        signals_task = run_database(
            lambda: self._signals.list_signals(
                symbol=normalized,
                outcome_status=None,
                source=None,
                include_archived=False,
                offset=0,
                limit=200,
            )
        )
        market_task = (
            self._load_web3(web3_item, timeframe=timeframe, history_days=history_days)
            if web3_item
            else self._load_market(normalized, asset_class, timeframe, history_days)
        )
        signal_result, market_result = await asyncio.gather(signals_task, market_task)
        signal_rows, _ = signal_result
        items = [item for item in workbench["items"] if item["symbol"] == normalized]
        item_ids = {item["id"] for item in items}
        notes = [item for item in workbench["notes"] if item["symbol"] == normalized]
        alerts = [item for item in workbench["alerts"] if item["symbol"] == normalized]
        events = [
            item for item in workbench["events"] if item.get("symbol") == normalized or item.get("entityId") in item_ids
        ]
        return AssetResearchResponse(
            symbol=normalized,
            assetClass=asset_class,
            timeframe=timeframe,
            currentPrice=market_result["currentPrice"],
            updatedAt=now,
            indicators=market_result["indicators"],
            history=market_result["history"],
            marketContext=market_result["marketContext"],
            watchItems=items,
            notes=notes,
            alerts=alerts,
            events=events,
            signals=signal_rows,
            issues=market_result["issues"],
        )

    async def _load_market(self, symbol: str, asset_class: str, timeframe: str, history_days: int) -> dict[str, Any]:
        issues: list[str] = []
        if asset_class == "cash":
            return {
                "currentPrice": 1.0,
                "indicators": None,
                "history": [],
                "marketContext": {"priceBasis": "USD"},
                "issues": [],
            }
        if asset_class == "index":
            try:
                start = (datetime.now(timezone.utc).date() - timedelta(days=history_days)).isoformat()
                response = await self._indexes.get_pricing_history_async(
                    symbol=symbol,
                    timeframe="1d",
                    start_date=start,
                )
                history = [
                    {
                        "timestamp": item.timestamp,
                        "open": item.open,
                        "high": item.high,
                        "low": item.low,
                        "close": item.close,
                        "volume": item.volume,
                    }
                    for item in response.data
                ]
                return {
                    "currentPrice": history[-1]["close"] if history else None,
                    "indicators": None,
                    "history": history,
                    "marketContext": {
                        "source": response.source,
                        "priceBasis": response.price_basis,
                        "pricingSymbol": response.pricing_symbol,
                    },
                    "issues": [] if history else ["所选区间没有代理价格"],
                }
            except Exception as exc:
                return {
                    "currentPrice": None,
                    "indicators": None,
                    "history": [],
                    "marketContext": {},
                    "issues": [str(exc)],
                }
        benchmark = "ETH/USDT" if symbol == "BTC/USDT" else "BTC/USDT"
        realtime_result, context_result, page_result, compare_result = await asyncio.gather(
            self._market_query.get_realtime(symbol=symbol, timeframe=timeframe, limit=500),
            self._binance.snapshot_service.get_market_page_snapshot_data(),
            self._binance.page.get_page(min_rise_pct=0, limit=100, quote_asset="USDT"),
            run_tool(lambda: self._pair_compare.compare_pairs(symbol, benchmark, 90, timeframe)),
            return_exceptions=True,
        )
        if isinstance(realtime_result, Exception):
            issues.append(str(realtime_result))
            current_price, indicators, history = None, None, []
        else:
            current_price = realtime_result.current_price
            indicators = realtime_result.indicators
            history = realtime_result.kline_data
        context: dict[str, Any] = {}
        if isinstance(context_result, Exception):
            issues.append(f"币安市场快照不可用：{context_result}")
        else:
            ticker_symbol = symbol.replace("/", "")
            for key in ("spot_ticker", "usdm_ticker", "usdm_mark"):
                row = next(
                    (
                        item
                        for item in context_result.get(key, {}).get("items", [])
                        if str(item.get("symbol") or "").upper() == ticker_symbol
                    ),
                    None,
                )
                if row:
                    context[key] = row
        if isinstance(page_result, Exception):
            issues.append(f"币安突破与排行数据不可用：{page_result}")
        else:
            page = page_result.model_dump(mode="json")
            ticker_symbol = symbol.replace("/", "")
            breakout = next(
                (row for row in page.get("monitor", {}).get("items", []) if row.get("symbol") == ticker_symbol),
                None,
            )
            if breakout:
                context["breakoutMonitor"] = breakout
            board_memberships = []
            for group_name in ("spot_boards", "contract_boards"):
                for board_name, board in page.get(group_name, {}).items():
                    row = next((item for item in board.get("items", []) if item.get("symbol") == ticker_symbol), None)
                    if row:
                        board_memberships.append({"group": group_name, "board": board_name, "data": row})
            context["marketBoardMemberships"] = board_memberships
        if isinstance(compare_result, Exception) or compare_result.get("error"):
            detail = compare_result if isinstance(compare_result, Exception) else compare_result.get("error")
            issues.append(f"基准对比不可用：{detail}")
        else:
            context["benchmarkComparison"] = {
                "benchmarkSymbol": benchmark,
                "days": 90,
                "timeframe": compare_result.get("timeframe"),
                "statistics": compare_result.get("statistics", {}),
            }
        return {
            "currentPrice": current_price,
            "indicators": indicators,
            "history": history,
            "marketContext": context,
            "issues": issues,
        }

    async def _load_web3(self, watch_item: dict[str, Any], *, timeframe: str, history_days: int) -> dict[str, Any]:
        source = dict(watch_item.get("sourceContext") or {})
        address = str(source.get("contractAddress") or watch_item["symbol"]).strip()
        chain_id = str(source.get("chainId") or "").strip() or None
        platform = str(source.get("platform") or "").strip() or None
        issues: list[str] = []
        rank_item: dict[str, Any] | None = None
        try:
            boards = await self._web3_heat_ranks.get_web3_heat_rank_boards(chain_id=chain_id, size=100)
            board = boards.boards.get("heat_score_desc")
            if board:
                matched = next(
                    (item for item in board.items if (item.contract_address or "").casefold() == address.casefold()),
                    None,
                )
                if matched:
                    rank_item = matched.model_dump(mode="json")
                    chain_id = chain_id or matched.chain_id
                    platform = platform or matched.platform
        except Exception as exc:
            issues.append(f"Web3 排行不可用：{exc}")

        calls: dict[str, Any] = {}
        if chain_id:
            calls["dynamic"] = self._web3_tokens.get_dynamic(chain_id=chain_id, contract_address=address)
            calls["audit"] = self._web3_tokens.get_audit(binance_chain_id=chain_id, contract_address=address)
        if platform:
            interval_ms = timeframe_to_milliseconds(timeframe)
            expected = int(history_days * 86_400_000 / interval_ms) if interval_ms > 0 else 500
            calls["kline"] = self._web3_tokens.get_kline(
                address=address,
                platform=platform,
                interval=timeframe,
                limit=min(1_000, max(240, expected)),
            )
        if not chain_id:
            issues.append("Web3 资产缺少 chainId，无法读取实时与审计数据")
        if not platform:
            issues.append("Web3 资产缺少 platform，无法读取 K 线")

        results = await asyncio.gather(*calls.values(), return_exceptions=True)
        loaded: dict[str, Any] = {}
        for key, result in zip(calls, results):
            if isinstance(result, Exception):
                issues.append(f"Web3 {key} 数据不可用：{result}")
            else:
                loaded[key] = result.model_dump(mode="json")

        history = [
            {
                "timestamp": int(item["open_time"]),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume") or 0),
            }
            for item in loaded.get("kline", {}).get("items", [])
            if all(item.get(field) is not None for field in ("open_time", "open", "high", "low", "close"))
        ]
        current_price = loaded.get("dynamic", {}).get("price")
        if current_price is None and rank_item:
            current_price = rank_item.get("metrics", {}).get("price")
        if current_price is None and history:
            current_price = history[-1]["close"]
        return {
            "currentPrice": current_price,
            "indicators": None,
            "history": history,
            "marketContext": {
                "chainId": chain_id,
                "platform": platform,
                "contractAddress": address,
                "web3Rank": rank_item,
                "web3Dynamic": loaded.get("dynamic"),
                "web3Audit": loaded.get("audit"),
            },
            "issues": issues,
        }
