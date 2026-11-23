"""Read verified Bitcoin block headers from public explorers."""
import httpx
from pydantic import BaseModel, PositiveInt

BitcoinHttpError = httpx.HTTPError


BITCOIN_DATA_SOURCES = ("https://mempool.space/api", "https://blockstream.info/api")


class BitcoinBlock(BaseModel):
    height: PositiveInt
    timestamp: PositiveInt


class BitcoinBlockClient:
    async def __aenter__(self):
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *_):
        await self._client.aclose()

    async def read_block(self, source, height=None):
        url = f"{source}/blocks" if height is None else f"{source}/blocks/{height}"
        response = await self._client.get(url)
        response.raise_for_status()
        block = BitcoinBlock.model_validate(response.json()[0])
        if height is not None and block.height != height:
            raise ValueError(f"Expected block {height}, got {block.height}")
        return block
