from __future__ import annotations

import asyncio

import httpx
from pydantic import BaseModel, PositiveInt

from app.contracts.dto.market_history import BitcoinHalvingResponse
from app.services.market.ttl_cache import TtlMemoryCache
from utils.logger import logger


HALVING_INTERVAL_BLOCKS = 210_000
BLOCK_INTERVAL_MS = 10 * 60 * 1000
FIRST_DYNAMIC_HALVING_HEIGHT = 1_050_000
BITCOIN_DATA_SOURCES = ("https://mempool.space/api", "https://blockstream.info/api")


class BitcoinBlock(BaseModel):
    height: PositiveInt
    timestamp: PositiveInt


class BitcoinHalvingService:
    def __init__(self) -> None:
        self._cache = TtlMemoryCache[str, BitcoinHalvingResponse](ttl_seconds=900)
        self._lock = asyncio.Lock()

    async def get_estimate(self) -> BitcoinHalvingResponse | None:
        async with self._lock:
            cached = self._cache.get("bitcoin")
            if cached is not None:
                return cached

            async with httpx.AsyncClient() as client:
                for source in BITCOIN_DATA_SOURCES:
                    try:
                        async with asyncio.timeout(5):
                            estimate = await self._estimate_from_source(client, source)
                    except (httpx.HTTPError, TimeoutError, ValueError, IndexError, KeyError, TypeError) as exc:
                        logger.warning("Bitcoin halving estimate could not read %s: %s", source, exc)
                        continue
                    self._cache.set("bitcoin", estimate)
                    return estimate
        return None

    @staticmethod
    async def _read_block(client: httpx.AsyncClient, url: str, height: int | None = None) -> BitcoinBlock:
        response = await client.get(url if height is None else f"{url}/{height}")
        response.raise_for_status()
        block = BitcoinBlock.model_validate(response.json()[0])
        if height is not None and block.height != height:
            raise ValueError(f"Expected block {height}, got {block.height}")
        return block

    async def _estimate_from_source(self, client: httpx.AsyncClient, source: str) -> BitcoinHalvingResponse:
        blocks_url = f"{source}/blocks"
        tip = await self._read_block(client, blocks_url)
        next_height = (tip.height // HALVING_INTERVAL_BLOCKS + 1) * HALVING_INTERVAL_BLOCKS
        confirmed = []
        for height in range(FIRST_DYNAMIC_HALVING_HEIGHT, next_height, HALVING_INTERVAL_BLOCKS):
            block = tip if height == tip.height else await self._read_block(client, blocks_url, height)
            confirmed.append(block.timestamp * 1000)
        tip_timestamp = tip.timestamp * 1000
        return BitcoinHalvingResponse(
            block_height=tip.height,
            block_timestamp=tip_timestamp,
            next_halving_height=next_height,
            estimated_at=tip_timestamp + (next_height - tip.height) * BLOCK_INTERVAL_MS,
            confirmed_halvings_after_2024=confirmed,
        )
