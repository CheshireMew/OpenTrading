from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.contracts.dto.equity_catalog import EquityCatalogResponse, EquityCatalogSourceResponse
from app.infra.cache import optional_cache_aget, optional_cache_aset
from app.services.market.equity_catalog_normalizers import (
    canonical_ticker, clean_name, equity_referral_url, make_listing, merge_listings, trade_url,
)
from utils.logger import logger


BINANCE = "https://www.binance.com"
BITGET = "https://api.bitget.com"
OKX = "https://www.okx.com"


@dataclass(frozen=True)
class CatalogSource:
    id: str
    platform: str
    label: str
    trading_type: str
    url: str


SOURCES = (
    CatalogSource("binance_stocks", "binance", "Binance Stocks", "spot", f"{BINANCE}/en/stocks-landing"),
    CatalogSource("binance_bstocks", "binance", "bStocks", "spot", f"{BINANCE}/en/markets/overview"),
    CatalogSource("binance_alpha", "binance", "Binance Alpha · Ondo", "spot", f"{BINANCE}/en/alpha"),
    CatalogSource("binance_perpetual", "binance", "Binance Futures", "perpetual", "https://fapi.binance.com/fapi/v1/exchangeInfo"),
    CatalogSource("okx_spot", "okx", "OKX Unified Tokenized Stocks", "spot", f"{OKX}/stock"),
    CatalogSource("okx_perpetual", "okx", "OKX Stock Perpetuals", "perpetual", f"{OKX}/api/v5/public/instruments?instType=SWAP"),
    CatalogSource("bitget_spot", "bitget", "Bitget Stocks · Reality / Ondo", "spot", "https://www.bitget.com/promotion/stock"),
    CatalogSource("bitget_stockplus", "bitget", "Bitget Stock+", "spot", "https://www.bitget.com/campaigns/bitget-stock-plus"),
    CatalogSource("bitget_perpetual", "bitget", "Bitget Stock Perpetuals", "perpetual", f"{BITGET}/api/v3/market/instruments?category=USDT-FUTURES"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def binance_stock_logo_url(value: str | None) -> str | None:
    path = str(value or "").strip()
    if not path:
        return None
    if path.startswith(("https://", "http://")):
        return path
    if path.startswith("//"):
        return f"https:{path}"
    if path.startswith("/"):
        return f"https://bin.bnbstatic.com{path}"
    return f"https://bin.bnbstatic.com/static/stock/{quote(path, safe='-_.')}"


def rows(value: Any) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Exchange catalog has an unexpected schema")
    return value


class EquityCatalogService:
    """Full source catalogs with independently retained last-successful results.

    Failed refreshes never turn a platform's support tags into confirmed absences.
    No account access or order endpoints are used.
    """

    def __init__(self, *, cache_service=None, transport: httpx.AsyncBaseTransport | None = None):
        self.cache_service = cache_service
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(25, connect=10), transport=transport,
            headers={"Accept": "application/json", "User-Agent": "Heimdall/2.0 (public market catalog)"},
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
            follow_redirects=True,
        )
        self._lock = asyncio.Lock()
        self._inflight: asyncio.Task | None = None
        self._snapshot: EquityCatalogResponse | None = None
        self._checked_at = 0.0
        self._last_sources: dict[str, dict] = {}
        self._cached_sources_loaded = False

    async def aclose(self):
        if self._inflight is not None and not self._inflight.done():
            self._inflight.cancel()
            await asyncio.gather(self._inflight, return_exceptions=True)
        await self._client.aclose()

    async def get_catalog(self, *, refresh: bool = False) -> EquityCatalogResponse:
        async with self._lock:
            if not refresh and self._snapshot is not None and time.monotonic() - self._checked_at < 300:
                return self._snapshot
            if self._inflight is None or self._inflight.done():
                self._inflight = asyncio.create_task(self._refresh())
            task = self._inflight
        return await asyncio.shield(task)

    async def _get(self, url: str, **params) -> Any:
        response = await self._client.get(url, params=params or None)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Exchange catalog has an unexpected schema")
        code = str(payload.get("code", ""))
        if code not in {"", "0", "00000", "000000"}:
            raise ValueError(f"Exchange rejected market catalog request ({code})")
        if payload.get("success") is False:
            raise ValueError("Exchange rejected market catalog request")
        return payload

    async def _refresh(self) -> EquityCatalogResponse:
        if not self._cached_sources_loaded:
            cached = await optional_cache_aget(self.cache_service, "equity-catalog:sources:v1")
            if isinstance(cached, dict):
                self._last_sources = cached
            self._cached_sources_loaded = True
        results = await asyncio.gather(*(self._fetch_source(source) for source in SOURCES), return_exceptions=True)
        source_statuses = []
        listings = []
        metadata = []
        for source, result in zip(SOURCES, results):
            error = None
            status = "ok"
            if isinstance(result, BaseException):
                logger.warning("Equity catalog source %s unavailable: %s", source.id, type(result).__name__)
                previous = self._last_sources.get(source.id)
                result = copy.deepcopy(previous) if previous else {"listings": [], "metadata": [], "updated_at": None}
                status = "stale" if previous else "unavailable"
                error = "catalog_not_verified" if source.id == "bitget_stockplus" else "refresh_failed" if previous else "source_unavailable"
            else:
                self._last_sources[source.id] = copy.deepcopy(result)
            listings.extend(result["listings"])
            metadata.extend(result.get("metadata", []))
            source_statuses.append(EquityCatalogSourceResponse(
                id=source.id, platform=source.platform, label=source.label,
                trading_type=source.trading_type, status=status,
                count=len({row["ticker"] for row in result["listings"]}),
                updated_at=result["updated_at"], error=error, url=equity_referral_url(source.url),
            ))
        items = merge_listings(listings, metadata)
        # Counts follow the same equity-exposure filtering as the visible list.
        for source in source_statuses:
            source.count = sum(any(o.source_id == source.id for o in item.offerings) for item in items)
        snapshot = EquityCatalogResponse(
            updated_at=utc_now(), complete=all(s.status == "ok" for s in source_statuses),
            items=items, sources=source_statuses,
        )
        await optional_cache_aset(self.cache_service, "equity-catalog:sources:v1", self._last_sources,
                                 ttl=86400, default_ttl=86400)
        self._snapshot = snapshot
        self._checked_at = time.monotonic()
        return snapshot

    async def _fetch_source(self, source: CatalogSource) -> dict:
        loader = getattr(self, f"_load_{source.id}")
        listings, metadata = await loader()
        return {"listings": listings, "metadata": metadata, "updated_at": utc_now()}

    async def _load_binance_stocks(self):
        info, names = await asyncio.gather(
            self._get(f"{BINANCE}/bapi/equity/v2/public/equity/symbol/get-exchange-info"),
            self._get(f"{BINANCE}/bapi/equity/v1/public/equity/symbol/get-symbols-static"),
        )
        metadata = [dict(ticker=canonical_ticker(r["s"]), name=r.get("n") or r["s"],
                         logo_url=binance_stock_logo_url(r.get("l") or r.get("logo")),
                         asset_type="etf" if r.get("t") in {"ETF", "FUND"} else "stock" if r.get("t") == "STOCK" else "unknown")
                    for r in rows(names.get("data")) if r.get("s")]
        name_map = {m["ticker"]: m for m in metadata}
        listings = []
        for r in rows(info.get("data", {}).get("syms")):
            if r.get("tr") not in {"BUY_SELL", "BUY", "SELL"} or not r.get("s"):
                continue
            ticker = canonical_ticker(r["s"])
            meta = name_map.get(ticker, {})
            listings.append(make_listing(
                ticker=ticker, name=meta.get("name", ticker), asset_type=meta.get("asset_type", "unknown"),
                platform="binance", trading_type="spot", product="Stocks", symbol=r["s"], quote_currency="USD",
                status=r["tr"], source_id="binance_stocks", url=f"{BINANCE}/en/trade/stocks/{r['s']}",
            ))
        return listings, metadata

    async def _load_binance_bstocks(self):
        payload = await self._get(f"{BINANCE}/bapi/asset/v2/public/asset-service/product/get-products", includeEtf="true")
        listings = []
        for r in rows(payload.get("data")):
            if "bStocks" not in r.get("tags", []) or r.get("st") not in {"TRADING", "HALT", "BREAK"}:
                continue
            base = r.get("b", "")
            if not base.endswith("B"):
                raise ValueError("Unexpected bStocks identifier")
            listings.append(make_listing(
                ticker=base[:-1], name=r.get("an", base), platform="binance", trading_type="spot",
                product="bStocks", symbol=r["s"], quote_currency=r["q"], source_id="binance_bstocks",
                status=r["st"], url=trade_url("binance", "spot", f"{base}_{r['q']}"),
            ))
        return listings, []

    async def _load_binance_alpha(self):
        payload = await self._get(f"{BINANCE}/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list")
        listings = []
        for r in rows(payload.get("data")):
            if not r.get("stockState") or r.get("offline") or r.get("fullyDelisted") or r.get("cexOffDisplay"):
                continue
            underlying = (r.get("rwaInfo") or {}).get("metaInfo", {}).get("ticker")
            if not underlying:
                raise ValueError("Tokenized security is missing its underlying ticker")
            listings.append(make_listing(
                ticker=underlying, name=r.get("name", underlying), platform="binance", trading_type="spot",
                product="Alpha · Ondo", symbol=r["symbol"], quote_currency="USDT", source_id="binance_alpha",
                status="sell_only" if r.get("offsell") else "trading",
                logo_url=r.get("iconUrl") or None,
                url=f"{BINANCE}/en/alpha/{r['chainId']}/{r['contractAddress']}",
            ))
        return listings, []

    async def _load_binance_perpetual(self):
        payload = await self._get("https://fapi.binance.com/fapi/v1/exchangeInfo")
        listings = []
        for r in rows(payload.get("symbols")):
            underlying_type = r.get("underlyingType", "")
            if not ("EQUITY" in underlying_type or underlying_type == "PREMARKET"):
                continue
            if r.get("contractType") not in {"TRADIFI_PERPETUAL", "PERPETUAL"} or r.get("status") not in {"TRADING", "HALT", "BREAK"}:
                continue
            # Binance reserves some crypto tickers, so the stock perpetual can
            # have a different ticker. Scope aliases here: STXX is also a real
            # leveraged ETF in the cash-equity catalog.
            ticker = {"STXX": "STX", "BBX": "BB", "USDEX": "USDE"}.get(r["baseAsset"], r["baseAsset"])
            market = {"KR_EQUITY": "KR", "HK_EQUITY": "HK", "CN_EQUITY": "CN"}.get(underlying_type, "")
            listings.append(make_listing(
                ticker=ticker, name=ticker, platform="binance", trading_type="perpetual", product="Futures",
                symbol=r["symbol"], quote_currency=r["quoteAsset"], source_id="binance_perpetual", market=market,
                status=r["status"], url=trade_url("binance", "perpetual", r["symbol"]),
            ))
        return listings, []

    async def _load_okx(self, trading_type: str):
        inst_type = "SPOT" if trading_type == "spot" else "SWAP"
        payload = await self._get(f"{OKX}/api/v5/public/instruments", instType=inst_type)
        listings = []
        for r in rows(payload.get("data")):
            if r.get("instCategory") != "3" or r.get("state") not in {"live", "suspend"}:
                continue
            base = r.get("baseCcy") if trading_type == "spot" else r.get("ctValCcy")
            if not base:
                raise ValueError("OKX equity instrument is missing its underlying identifier")
            ticker = base[1:] if trading_type == "spot" and base.startswith("X") else base
            listings.append(make_listing(
                ticker=ticker, name=ticker, platform="okx", trading_type=trading_type,
                product="Unified Tokenized Stocks" if trading_type == "spot" else "Stock Perpetuals",
                symbol=r["instId"], quote_currency=r.get("quoteCcy") or r.get("settleCcy", ""),
                source_id=f"okx_{trading_type}", status=r["state"], url=trade_url("okx", trading_type, r["instId"]),
            ))
        return listings, []

    async def _load_okx_spot(self):
        return await self._load_okx("spot")

    async def _load_okx_perpetual(self):
        return await self._load_okx("perpetual")

    async def _load_bitget(self, trading_type: str):
        categories = ["SPOT"] if trading_type == "spot" else ["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]
        payloads = await asyncio.gather(*(self._get(f"{BITGET}/api/v3/market/instruments", category=c) for c in categories))
        listings = []
        metadata = []
        for payload in payloads:
            for r in rows(payload.get("data")):
                if r.get("symbolType") != "stock" and r.get("isReality") != "yes":
                    continue
                if r.get("status") not in {"online", "suspend", "restrictedAPI"}:
                    continue
                if trading_type == "perpetual" and r.get("type") != "perpetual":
                    continue
                base = r.get("baseCoin", "")
                if r.get("isReality") == "yes":
                    ticker, product = base[1:], "Reality"
                elif base.upper().endswith("ON"):
                    ticker, product = base[:-2], "Ondo"
                elif trading_type == "spot" and base.upper().endswith("X"):
                    ticker, product = base[:-1], "xStocks"
                else:
                    ticker, product = base, "Stock Perpetuals" if trading_type == "perpetual" else "Stocks"
                name = clean_name(r.get("fullName") or ticker)
                kind = r.get("instrumentType", "unknown")
                if kind not in {"stock", "etf", "index"}:
                    kind = "unknown"
                listing = make_listing(
                    ticker=ticker, name=name, platform="bitget", trading_type=trading_type, product=product,
                    symbol=r["symbol"], quote_currency=r["quoteCoin"], source_id=f"bitget_{trading_type}",
                    status=r["status"], market=r.get("marketRegion") or "", asset_type=kind,
                    url=trade_url("bitget", trading_type, r["symbol"]),
                )
                listings.append(listing)
                if name != ticker:
                    metadata.append(dict(ticker=listing["ticker"], name=name, asset_type=listing["asset_type"]))
        return listings, metadata

    async def _load_bitget_spot(self):
        return await self._load_bitget("spot")

    async def _load_bitget_stockplus(self):
        # Documented Stock+ market endpoints require authorized credentials
        # and known symbols. A complete tradable catalog is not yet verified.
        # Never infer support from the wider US stock market or Reality catalog.
        raise ValueError("Stock+ complete trading catalog has not been verified")

    async def _load_bitget_perpetual(self):
        return await self._load_bitget("perpetual")
