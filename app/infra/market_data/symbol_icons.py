"""Discover current asset logos from Binance; cache public images, never user data."""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx

ASSET_INDEX_URL = "https://www.binance.com/bapi/asset/v2/public/asset/asset/get-all-asset"
LOGO_HOSTS = {"bin.bnbstatic.com", "public.bnbstatic.com", "s2.coinmarketcap.com"}
INDEX_TTL = 6 * 3600
IMAGE_TTL = 86400
RETRY_TTL = 60
MAX_IMAGE_BYTES = 1024 * 1024
MAX_CACHE_BYTES = 8 * 1024 * 1024
MAX_CACHE_ITEMS = 512


@dataclass(frozen=True)
class SymbolIcon:
    content: bytes
    media_type: str
    etag: str


def logo_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    url = urlparse(value)
    return value if url.scheme == "https" and url.hostname in LOGO_HOSTS else None


def image_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


class SymbolIconClient:
    def __init__(self, transport=None, clock=time.monotonic):
        self.client = httpx.AsyncClient(transport=transport, timeout=10)
        self.clock = clock
        self.index: dict[str, str] = {}
        self.refresh_at = 0.0
        self.discover_at = 0.0
        self.index_lock = asyncio.Lock()
        self.cache: OrderedDict[str, tuple[float, SymbolIcon | None]] = OrderedDict()
        self.cache_bytes = 0
        self.pending: dict[str, asyncio.Task] = {}
        self.closed = False

    async def refresh(self, missing_asset: str):
        def due():
            return self.clock() >= self.refresh_at or (
                bool(self.index) and missing_asset not in self.index and self.clock() >= self.discover_at)
        if not due():
            return
        async with self.index_lock:
            if not due():
                return
            self.refresh_at = self.clock() + RETRY_TTL
            self.discover_at = self.clock() + RETRY_TTL
            try:
                response = await self.client.get(ASSET_INDEX_URL)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or payload.get("code") != "000000" or not isinstance(payload.get("data"), list):
                    return
                found = {}
                for row in payload["data"]:
                    if not isinstance(row, dict):
                        continue
                    asset = row.get("assetCode")
                    url = logo_url(row.get("fullLogoUrl")) or logo_url(row.get("logoUrl"))
                    if isinstance(asset, str) and url:
                        found[asset.upper()] = url
                if found:
                    self.index = found
                    self.refresh_at = self.clock() + INDEX_TTL
            except (httpx.HTTPError, ValueError):
                pass  # Retain the last verified catalog through an upstream outage.

    async def download(self, url: str) -> SymbolIcon | None:
        try:
            async with self.client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                if not logo_url(str(response.url)):
                    return None
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_IMAGE_BYTES:
                        return None
                media_type = image_type(content)
                if media_type:
                    data = bytes(content)
                    return SymbolIcon(data, media_type, '"' + hashlib.sha256(data).hexdigest() + '"')
        except httpx.HTTPError:
            pass
        return None

    def remember(self, asset: str, icon: SymbolIcon | None):
        old = self.cache.pop(asset, None)
        if old and old[1]:
            self.cache_bytes -= len(old[1].content)
        self.cache[asset] = (self.clock() + (IMAGE_TTL if icon else RETRY_TTL), icon)
        if icon:
            self.cache_bytes += len(icon.content)
        while len(self.cache) > MAX_CACHE_ITEMS or self.cache_bytes > MAX_CACHE_BYTES:
            _, (_, previous) = self.cache.popitem(last=False)
            if previous:
                self.cache_bytes -= len(previous.content)

    async def load(self, asset: str, stale: SymbolIcon | None):
        await self.refresh(asset)
        name = asset
        # Binance contract multipliers are not separate coins. Prefer an exact
        # catalog entry (e.g. 1000SATS) before resolving a scaled contract.
        if name not in self.index:
            match = re.fullmatch(r"(?:1000|10000|1000000|1M)([A-Z][A-Z0-9]*)", asset)
            if match and match[1] in self.index:
                name = match[1]
        candidates = [self.index.get(name), f"https://bin.bnbstatic.com/static/assets/logos/{quote(name, safe='')}.png"]
        for url in dict.fromkeys(value for value in candidates if value):
            icon = await self.download(url)
            if icon:
                self.remember(asset, icon)
                return icon
        self.remember(asset, stale)
        if stale:
            self.cache[asset] = (self.clock() + RETRY_TTL, stale)
        return stale

    async def get(self, asset: str) -> SymbolIcon | None:
        if self.closed or not re.fullmatch(r"[A-Z0-9._-]{1,40}", asset):
            return None
        cached = self.cache.get(asset)
        if cached and cached[0] > self.clock():
            self.cache.move_to_end(asset)
            return cached[1]
        task = self.pending.get(asset)
        if task is None:
            task = asyncio.create_task(self.load(asset, cached[1] if cached else None))
            self.pending[asset] = task
            task.add_done_callback(lambda completed: self.pending.pop(asset, None))
        return await asyncio.shield(task)

    async def aclose(self):
        self.closed = True
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.client.aclose()
