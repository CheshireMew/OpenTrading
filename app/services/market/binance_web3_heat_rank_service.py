from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from app.contracts.dto.binance.web3 import BinanceWeb3HeatRankBoardsResponse
from .binance_numbers import to_int
from .binance_web3_heat_rank import BinanceWeb3HeatRankComposer
from .binance_web3_rank_gateway import BinanceWeb3RankGateway
from .binance_web3_support import SUPPORTED_WEB3_CHAIN_IDS, WEB3_ALL_CHAINS_ID, normalize_web3_chain_id
from .market_board_support import board_key, compare_text, sort_rows_by_number
from app.infra.ttl_cache import TtlMemoryCache


HEAT_RANK_BOARDS_CACHE_TTL_SECONDS = 20.0


def sort_heat_rank_items(items: list[dict[str, Any]], field: str, direction: str) -> list[dict[str, Any]]:
    return sort_rows_by_number(
        items,
        field,
        direction,
        value_getter=_heat_rank_sort_value,
        tie_breaker=_heat_rank_tie_breaker,
    )


def _heat_rank_sort_value(item: dict[str, Any], field: str) -> Any:
    if field == "heat_score":
        return item.get("heat_score")
    return (item.get("metrics") or {}).get(field)


def _heat_rank_tie_breaker(left: dict[str, Any], right: dict[str, Any]) -> int:
    left_rank = to_int(left.get("rank")) or 0
    right_rank = to_int(right.get("rank")) or 0
    if left_rank != right_rank:
        return left_rank - right_rank
    return compare_text(left.get("symbol"), right.get("symbol"))


class BinanceWeb3HeatRankService:
    def __init__(self, rank_gateway: BinanceWeb3RankGateway) -> None:
        self.rank_gateway = rank_gateway
        self.heat_rank_composer = BinanceWeb3HeatRankComposer()
        self._boards_cache: TtlMemoryCache[tuple[str | None, int], BinanceWeb3HeatRankBoardsResponse] = TtlMemoryCache(
            HEAT_RANK_BOARDS_CACHE_TTL_SECONDS,
            copy_value=deepcopy,
        )

    async def get_web3_heat_rank_boards(
        self,
        *,
        chain_id: str | None = None,
        size: int = 30,
    ) -> BinanceWeb3HeatRankBoardsResponse:
        resolved_chain_id = normalize_web3_chain_id(chain_id)
        response_chain_id = resolved_chain_id or WEB3_ALL_CHAINS_ID
        cache_key = (resolved_chain_id, int(size))
        cached = self._boards_cache.get(cache_key)
        if cached is not None:
            return cached
        items = await self._compose_web3_heat_rank_items(resolved_chain_id=resolved_chain_id, response_chain_id=response_chain_id, size=size)
        formula = self._heat_rank_formula()
        boards = {
            board_key(field, direction): {
                "source": "binance-web3",
                "leaderboard": "web3_heat_rank",
                "chain_id": response_chain_id,
                "size": size,
                "items": sort_heat_rank_items(items, field, direction)[:size],
                "formula": formula,
            }
            for field in ("heat_score", "percent_change_24h", "market_cap", "liquidity")
            for direction in ("desc", "asc")
        }
        response = BinanceWeb3HeatRankBoardsResponse.model_validate({
            "source": "binance-web3",
            "leaderboard": "web3_heat_rank_boards",
            "chain_id": response_chain_id,
            "size": size,
            "boards": boards,
            "formula": formula,
        })
        self._boards_cache.set(cache_key, response)
        return response

    async def _compose_web3_heat_rank_items(
        self,
        *,
        resolved_chain_id: str | None,
        response_chain_id: str,
        size: int,
    ) -> list[dict[str, Any]]:
        source_size = min(100, max(50, size * 2))
        (
            top_search,
            trending,
            volume_rank,
            tx_rank,
            unique_rank,
            social_hype,
            smart_money,
            meme_rank,
        ) = await asyncio.gather(
            self._safe_rank_call(
                self.rank_gateway.get_unified_token_rank(rank_type=11, chain_id=resolved_chain_id, period=50, sort_by=2, size=source_size),
                "top_search",
            ),
            self._safe_rank_call(
                self.rank_gateway.get_unified_token_rank(rank_type=10, chain_id=resolved_chain_id, period=50, sort_by=0, size=source_size),
                "trending",
            ),
            self._safe_rank_call(
                self.rank_gateway.get_unified_token_rank(rank_type=10, chain_id=resolved_chain_id, period=50, sort_by=70, size=source_size),
                "volume_rank",
            ),
            self._safe_rank_call(
                self.rank_gateway.get_unified_token_rank(rank_type=10, chain_id=resolved_chain_id, period=50, sort_by=60, size=source_size),
                "transaction_rank",
            ),
            self._safe_rank_call(
                self.rank_gateway.get_unified_token_rank(rank_type=10, chain_id=resolved_chain_id, period=50, sort_by=100, size=source_size),
                "unique_trader_rank",
            ),
            self._safe_rank_call(
                self._get_heat_rank_social_hype(chain_id=resolved_chain_id),
                "social_hype",
            ),
            self._safe_rank_call(
                self._get_heat_rank_smart_money(chain_id=resolved_chain_id),
                "smart_money_inflow",
            ),
            self._safe_rank_call(
                self._get_heat_rank_meme(chain_id=resolved_chain_id),
                "meme_rank",
            ),
        )
        return self.heat_rank_composer.compose(
            chain_id=response_chain_id,
            top_search=top_search.get("items") or [],
            trending=trending.get("items") or [],
            volume_rank=volume_rank.get("items") or [],
            tx_rank=tx_rank.get("items") or [],
            unique_rank=unique_rank.get("items") or [],
            social_hype=social_hype.get("items") or [],
            smart_money=smart_money.get("items") or [],
            meme_rank=meme_rank.get("items") or [],
        )

    def _heat_rank_formula(self) -> dict[str, list[str]]:
        return {
            "positive": [
                "top_search_rank",
                "trending_rank",
                "social_hype",
                "volume_growth",
                "transaction_growth",
                "unique_traders",
                "smart_money_inflow",
                "meme_rank",
            ],
            "penalty": ["low_liquidity", "contract_risk"],
        }

    async def _get_heat_rank_social_hype(self, *, chain_id: str | None) -> dict[str, Any]:
        if chain_id is not None:
            return await self.rank_gateway.get_social_hype_leaderboard(chain_id=chain_id, target_language="zh")
        results = await asyncio.gather(
            *[
                self._safe_rank_call(
                    self.rank_gateway.get_social_hype_leaderboard(chain_id=supported_chain_id, target_language="zh"),
                    f"social_hype:{supported_chain_id}",
                )
                for supported_chain_id in SUPPORTED_WEB3_CHAIN_IDS
            ]
        )
        return {
            "source": "binance-web3",
            "leaderboard": "social_hype",
            "items": [item for result in results for item in result.get("items", [])],
        }

    async def _get_heat_rank_smart_money(self, *, chain_id: str | None) -> dict[str, Any]:
        if chain_id is not None:
            return await self.rank_gateway.get_smart_money_inflow_rank(chain_id=chain_id, period="24h")
        results = await asyncio.gather(
            *[
                self._safe_rank_call(
                    self.rank_gateway.get_smart_money_inflow_rank(chain_id=supported_chain_id, period="24h"),
                    f"smart_money_inflow:{supported_chain_id}",
                )
                for supported_chain_id in SUPPORTED_WEB3_CHAIN_IDS
            ]
        )
        return {
            "source": "binance-web3",
            "leaderboard": "smart_money_inflow",
            "items": [item for result in results for item in result.get("items", [])],
        }

    async def _get_heat_rank_meme(self, *, chain_id: str | None) -> dict[str, Any]:
        if chain_id not in (None, "56"):
            return {
                "source": "binance-web3",
                "leaderboard": "meme_rank",
                "items": [],
            }
        return await self.rank_gateway.get_meme_rank(chain_id="56")

    async def _safe_rank_call(self, awaitable: Any, leaderboard: str) -> dict[str, Any]:
        try:
            response = await asyncio.wait_for(awaitable, timeout=12)
            return response.model_dump() if hasattr(response, "model_dump") else response
        except Exception as exc:
            return {
                "source": "binance-web3",
                "leaderboard": leaderboard,
                "items": [],
                "error": str(exc),
            }
