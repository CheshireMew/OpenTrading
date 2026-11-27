from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


WEB3_ALL_CHAIN_ID = "all"


@dataclass(frozen=True)
class Web3Chain:
    chain_id: str
    label: str
    platform: str


WEB3_CHAIN_CATALOG = (
    Web3Chain(chain_id="1", label="Ethereum", platform="ethereum"),
    Web3Chain(chain_id="56", label="BSC", platform="bsc"),
    Web3Chain(chain_id="8453", label="Base", platform="base"),
    Web3Chain(chain_id="CT_501", label="Solana", platform="solana"),
)

WEB3_CHAIN_BY_ID = {chain.chain_id: chain for chain in WEB3_CHAIN_CATALOG}
WEB3_CHAIN_BY_PLATFORM = {chain.platform: chain for chain in WEB3_CHAIN_CATALOG}


def normalize_web3_address(address: str, platform: str) -> str:
    value = str(address).strip()
    return value if platform == "solana" else value.lower()


def is_web3_address(address: str, platform: str) -> bool:
    pattern = r"[1-9A-HJ-NP-Za-km-z]{32,44}" if platform == "solana" else r"0x[0-9a-fA-F]{40}"
    return bool(re.fullmatch(pattern, address))


def web3_storage_symbol(address: str, platform: str) -> str:
    from app.domain.market.constants import KLINE_SYMBOL_MAX_LENGTH

    candidate = f"WEB3:{platform}:{normalize_web3_address(address, platform)}"
    if len(candidate) <= KLINE_SYMBOL_MAX_LENGTH:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:40]
    prefix_length = max(1, KLINE_SYMBOL_MAX_LENGTH - len("WEB3::") - len(digest))
    return f"WEB3:{platform[:prefix_length]}:{digest}"


__all__ = [
    "WEB3_ALL_CHAIN_ID",
    "WEB3_CHAIN_BY_ID",
    "WEB3_CHAIN_BY_PLATFORM",
    "WEB3_CHAIN_CATALOG",
    "Web3Chain",
    "normalize_web3_address",
    "is_web3_address",
    "web3_storage_symbol",
]
