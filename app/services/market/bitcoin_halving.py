from __future__ import annotations

import asyncio

from app.infra.market_data.bitcoin import BITCOIN_DATA_SOURCES, BitcoinBlockClient, BitcoinHttpError

from app.contracts.dto.market_history import BitcoinHalvingResponse
from app.infra.ttl_cache import TtlMemoryCache
from utils.logger import logger


HALVING_INTERVAL_BLOCKS = 210_000
BLOCK_INTERVAL_MS = 10 * 60 * 1000
FIRST_DYNAMIC_HALVING_HEIGHT = 1_050_000
class BitcoinHalvingService:
    def __init__(self) -> None:
        self._cache = TtlMemoryCache[str, BitcoinHalvingResponse](ttl_seconds=900)
        self._lock = asyncio.Lock()

    async def get_estimate(self) -> BitcoinHalvingResponse | None:
        async with self._lock:
            cached = self._cache.get("bitcoin")
            if cached is not None:
                return cached

            async with BitcoinBlockClient() as client:
                for source in BITCOIN_DATA_SOURCES:
                    try:
                        async with asyncio.timeout(5):
                            estimate = await self._estimate_from_source(client, source)
                    except (BitcoinHttpError, TimeoutError, ValueError, IndexError, KeyError, TypeError) as exc:
                        logger.warning("Bitcoin halving estimate could not read %s: %s", source, exc)
                        continue
                    self._cache.set("bitcoin", estimate)
                    return estimate
        return None

    async def _estimate_from_source(self, client: BitcoinBlockClient, source: str) -> BitcoinHalvingResponse:
        tip = await client.read_block(source)
        next_height = (tip.height // HALVING_INTERVAL_BLOCKS + 1) * HALVING_INTERVAL_BLOCKS
        confirmed = []
        for height in range(FIRST_DYNAMIC_HALVING_HEIGHT, next_height, HALVING_INTERVAL_BLOCKS):
            block = tip if height == tip.height else await client.read_block(source, height)
            confirmed.append(block.timestamp * 1000)
        tip_timestamp = tip.timestamp * 1000
        return BitcoinHalvingResponse(
            block_height=tip.height,
            block_timestamp=tip_timestamp,
            next_halving_height=next_height,
            estimated_at=tip_timestamp + (next_height - tip.height) * BLOCK_INTERVAL_MS,
            confirmed_halvings_after_2024=confirmed,
        )
