from __future__ import annotations

from typing import Any

from app.domain.market.web3_chains import (
    WEB3_ALL_CHAIN_ID,
    WEB3_CHAIN_BY_ID,
    WEB3_CHAIN_CATALOG,
)
from .binance_numbers import safe_float, to_float, to_int

WEB3_ALL_CHAINS_ID = WEB3_ALL_CHAIN_ID
SUPPORTED_WEB3_CHAIN_IDS = tuple(chain.chain_id for chain in WEB3_CHAIN_CATALOG)


def asset_url(path: Any) -> str | None:
    if path in (None, ""):
        return None
    value = str(path).strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("//"):
        return f"https:{value}"
    return f"https://bin.bnbstatic.com{value}"


def normalize_rank_token(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": item.get("symbol"),
        "chain_id": item.get("chainId"),
        "contract_address": item.get("contractAddress"),
        "icon_url": asset_url(item.get("icon")),
        "price": to_float(item.get("price")),
        "market_cap": to_float(item.get("marketCap")),
        "liquidity": to_float(item.get("liquidity")),
        "holders": to_int(item.get("holders")),
        "launch_time": to_int(item.get("launchTime")),
        "percent_change_1h": to_float(item.get("percentChange1h")),
        "percent_change_24h": to_float(item.get("percentChange24h")),
        "volume_1h": to_float(item.get("volume1h")),
        "volume_4h": to_float(item.get("volume4h")),
        "volume_24h": to_float(item.get("volume24h")),
        "count_1h": to_int(item.get("count1h")),
        "count_24h": to_int(item.get("count24h")),
        "unique_trader_1h": to_int(item.get("uniqueTrader1h")),
        "unique_trader_24h": to_int(item.get("uniqueTrader24h")),
        "kyc_holders": to_int(item.get("kycHolders")),
        "audit_info": item.get("auditInfo") or {},
    }


def normalize_token_dynamic(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "price": to_float(data.get("price")),
        "native_token_price": to_float(data.get("nativeTokenPrice")),
        "volume_24h": to_float(data.get("volume24h")),
        "volume_24h_buy": to_float(data.get("volume24hBuy")),
        "volume_24h_sell": to_float(data.get("volume24hSell")),
        "volume_4h": to_float(data.get("volume4h")),
        "volume_1h": to_float(data.get("volume1h")),
        "volume_5m": to_float(data.get("volume5m")),
        "count_24h": to_int(data.get("count24h")),
        "count_24h_buy": to_int(data.get("count24hBuy")),
        "count_24h_sell": to_int(data.get("count24hSell")),
        "percent_change_5m": to_float(data.get("percentChange5m")),
        "percent_change_1h": to_float(data.get("percentChange1h")),
        "percent_change_4h": to_float(data.get("percentChange4h")),
        "percent_change_24h": to_float(data.get("percentChange24h")),
        "market_cap": to_float(data.get("marketCap")),
        "fdv": to_float(data.get("fdv")),
        "total_supply": to_float(data.get("totalSupply")),
        "circulating_supply": to_float(data.get("circulatingSupply")),
        "price_high_24h": to_float(data.get("priceHigh24h")),
        "price_low_24h": to_float(data.get("priceLow24h")),
        "holders": to_int(data.get("holders")),
        "liquidity": to_float(data.get("liquidity")),
        "launch_time": to_int(data.get("launchTime")),
        "top10_holders_percentage": to_float(data.get("top10HoldersPercentage")),
        "kyc_holder_count": to_int(data.get("kycHolderCount")),
        "kol_holders": to_int(data.get("kolHolders")),
        "kol_holding_percent": to_float(data.get("kolHoldingPercent")),
        "pro_holders": to_int(data.get("proHolders")),
        "pro_holding_percent": to_float(data.get("proHoldingPercent")),
        "smart_money_holders": to_int(data.get("smartMoneyHolders")),
        "smart_money_holding_percent": to_float(data.get("smartMoneyHoldingPercent")),
    }
def token_key(item: dict[str, Any]) -> str | None:
    chain_id = item.get("chain_id") or item.get("chainId")
    contract_address = item.get("contract_address") or item.get("contractAddress")
    symbol = item.get("symbol")
    if chain_id and contract_address:
        return f"{chain_id}:{str(contract_address).lower()}"
    if chain_id and symbol:
        return f"{chain_id}:symbol:{str(symbol).upper()}"
    return None


def chain_platform(chain_id: Any) -> str | None:
    chain = WEB3_CHAIN_BY_ID.get(str(chain_id))
    return chain.platform if chain else None


def normalize_web3_chain_id(chain_id: Any) -> str | None:
    if chain_id is None:
        return None
    value = str(chain_id).strip()
    if not value or value.lower() == WEB3_ALL_CHAINS_ID:
        return None
    return value


def ratio_score(value: Any, max_value: float | int | None) -> float:
    numeric = safe_float(value)
    max_numeric = safe_float(max_value)
    if numeric is None or max_numeric is None or numeric <= 0 or max_numeric <= 0:
        return 0
    return min(1, numeric / max_numeric)
