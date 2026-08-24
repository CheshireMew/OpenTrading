from __future__ import annotations

from dataclasses import dataclass


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


__all__ = [
    "WEB3_ALL_CHAIN_ID",
    "WEB3_CHAIN_BY_ID",
    "WEB3_CHAIN_CATALOG",
    "Web3Chain",
]
