from __future__ import annotations

import hashlib
import time
import uuid

from app.application.errors import InvalidRequestError
from app.contracts.dto.binance.web3 import (
    BinanceWeb3TokenAuditResponse,
    BinanceWeb3TokenDynamicResponse,
    BinanceWeb3TokenKlineResponse,
)
from app.domain.market.constants import KLINE_SYMBOL_MAX_LENGTH, timeframe_to_milliseconds
from app.services.market.history_range_coordinator import HistoryRangeCoordinator, merge_ohlcv_rows
from app.services.market.history_ranges import is_recent_cache_usable
from app.application.persistence_ports import KlineStorePort

from .binance_api_support import BinanceApiSupport, compact_query
from .binance_numbers import to_float, to_int
from .binance_web3_support import normalize_token_dynamic


class BinanceWeb3TokenService:
    def __init__(self, *, web3_client: BinanceApiSupport, kline_client: BinanceApiSupport, kline_store: KlineStorePort) -> None:
        self.web3_client = web3_client
        self.kline_client = kline_client
        self.kline_store = kline_store
        self.history_ranges = HistoryRangeCoordinator(kline_store)

    async def get_dynamic(self, *, chain_id: str | None = None, contract_address: str | None = None) -> BinanceWeb3TokenDynamicResponse:
        if not chain_id or not contract_address:
            raise InvalidRequestError("chain_id and contract_address are required")
        payload = await self.web3_client.get_json(
            "/bapi/defi/v4/public/wallet-direct/buw/wallet/market/token/dynamic/info/ai",
            params={"chainId": chain_id, "contractAddress": contract_address},
            ttl=30,
        )
        return BinanceWeb3TokenDynamicResponse.model_validate({
            "source": "binance-web3",
            "chain_id": chain_id,
            "contract_address": contract_address,
            **normalize_token_dynamic(payload.get("data") or {}),
        })

    async def get_kline(
        self,
        *,
        address: str | None = None,
        platform: str | None = None,
        interval: str | None = None,
        limit: int | None = None,
        from_time: int | None = None,
        to_time: int | None = None,
        pm: str | None = None,
    ) -> BinanceWeb3TokenKlineResponse:
        if not address or not platform or not interval:
            raise InvalidRequestError("address, platform and interval are required")

        address_key = address.strip().lower()
        platform_key = platform.strip().lower()
        interval_key = interval.strip()
        limit_value = int(limit or 240)
        storage_symbol = self._storage_symbol(address=address_key, platform=platform_key)
        end_ts = to_time or int(time.time() * 1000)
        interval_ms = timeframe_to_milliseconds(interval_key)

        if interval_ms <= 0:
            rows = await self._fetch_kline_rows(
                address=address_key,
                platform=platform_key,
                interval=interval_key,
                limit=limit_value,
                from_time=from_time,
                to_time=to_time,
                pm=pm,
            )
            self.kline_store.save(storage_symbol, interval_key, rows)
            return self._build_kline_response(address=address_key, platform=platform_key, interval=interval_key, rows=rows[-limit_value:])

        start_ts = from_time if from_time is not None else end_ts - (interval_ms * max(limit_value, 1))
        end_ts_exclusive = end_ts + 1
        cached_result = self.history_ranges.read_cached(
            storage_symbol=storage_symbol,
            timeframe=interval_key,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
        )
        cached_rows = cached_result.rows
        if from_time is None and to_time is None and is_recent_cache_usable(
            cached=cached_rows,
            timeframe=interval_key,
            limit=limit_value,
            now_ms=end_ts,
        ):
            return self._build_kline_response(
                address=address_key,
                platform=platform_key,
                interval=interval_key,
                rows=cached_rows[-limit_value:],
            )

        async def fetch_gap(gap_start: int, gap_end: int) -> list[list[float]]:
            return await self._fetch_kline_rows(
                address=address_key,
                platform=platform_key,
                interval=interval_key,
                limit=limit_value,
                from_time=gap_start,
                to_time=max(gap_start, gap_end - 1),
                pm=pm,
            )

        range_result = await self.history_ranges.load_async(
            storage_symbol=storage_symbol,
            timeframe=interval_key,
            start_ts=start_ts,
            end_ts_exclusive=end_ts_exclusive,
            fetch_gap=fetch_gap,
            cached_rows=cached_rows,
        )
        return self._build_kline_response(
            address=address_key,
            platform=platform_key,
            interval=interval_key,
            rows=range_result.rows[-limit_value:],
        )

    async def get_audit(self, *, binance_chain_id: str | None = None, contract_address: str | None = None) -> BinanceWeb3TokenAuditResponse:
        if not binance_chain_id or not contract_address:
            raise InvalidRequestError("binance_chain_id and contract_address are required")
        payload = await self.web3_client.post_json(
            "/bapi/defi/v1/public/wallet-direct/security/token/audit",
            body={
                "binanceChainId": binance_chain_id,
                "contractAddress": contract_address,
                "requestId": str(uuid.uuid4()),
            },
            extra_headers={"Content-Type": "application/json", "source": "agent"},
            ttl=30,
        )
        data = payload.get("data") or {}
        return BinanceWeb3TokenAuditResponse.model_validate({
            "source": "binance-web3",
            "binance_chain_id": binance_chain_id,
            "contract_address": contract_address,
            "has_result": bool(data.get("hasResult")),
            "is_supported": bool(data.get("isSupported")),
            "risk_level_enum": data.get("riskLevelEnum"),
            "risk_level": to_int(data.get("riskLevel")),
            "buy_tax": to_float((data.get("extraInfo") or {}).get("buyTax")),
            "sell_tax": to_float((data.get("extraInfo") or {}).get("sellTax")),
            "is_verified": (data.get("extraInfo") or {}).get("isVerified"),
            "risk_items": data.get("riskItems") or [],
        })

    async def _fetch_kline_rows(
        self,
        *,
        address: str,
        platform: str,
        interval: str,
        limit: int,
        from_time: int | None,
        to_time: int | None,
        pm: str | None,
    ) -> list[list[float]]:
        payload = await self.kline_client.get_json(
            "/u-kline/v1/k-line/candles",
            params=compact_query(
                {
                    "address": address,
                    "platform": platform,
                    "interval": interval,
                    "limit": limit,
                    "from": from_time,
                    "to": to_time,
                    "pm": pm or "p",
                }
            ),
            ttl=30,
            use_cache=False,
        )
        return self._normalize_kline_rows(payload.get("data") or [])

    def _build_kline_response(
        self,
        *,
        address: str,
        platform: str,
        interval: str,
        rows: list[list[float]],
    ) -> BinanceWeb3TokenKlineResponse:
        return BinanceWeb3TokenKlineResponse.model_validate({
            "source": "binance-web3",
            "address": address,
            "platform": platform,
            "interval": interval,
            "items": [
                {
                    "open_time": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "trade_count": None,
                }
                for row in rows
            ],
        })

    def _normalize_kline_rows(self, rows: list) -> list[list[float]]:
        normalized: list[list[float]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) <= 5:
                continue
            open_time = to_int(row[5])
            open_price = to_float(row[0])
            high = to_float(row[1])
            low = to_float(row[2])
            close = to_float(row[3])
            volume = to_float(row[4])
            if None in (open_time, open_price, high, low, close, volume):
                continue
            normalized.append([open_time, open_price, high, low, close, volume])
        return merge_ohlcv_rows(normalized)

    @staticmethod
    def _storage_symbol(*, address: str, platform: str) -> str:
        candidate = f"WEB3:{platform}:{address}"
        if len(candidate) <= KLINE_SYMBOL_MAX_LENGTH:
            return candidate
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:40]
        platform_prefix_length = max(1, KLINE_SYMBOL_MAX_LENGTH - len("WEB3::") - len(digest))
        return f"WEB3:{platform[:platform_prefix_length]}:{digest}"
