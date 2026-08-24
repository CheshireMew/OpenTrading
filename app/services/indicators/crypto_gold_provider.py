"""
使用 Binance API 获取黄金价格（通过 PAXG - Paxos Gold）
PAXG 是锚定实物黄金的代币，1 PAXG = 1 盎司黄金
"""
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from .base_provider import BaseIndicatorProvider, logger
from app.infra.executor import run_external_io

class CryptoGoldProvider(BaseIndicatorProvider):
    """
    通过加密货币交易所获取黄金价格
    使用 PAXG/USDT (Paxos Gold)
    """

    def __init__(self):
        super().__init__()
        self.exchange = None

    async def _fetch_gold_price(self) -> Optional[Dict[str, Any]]:
        """获取黄金价格（通过PAXG）"""
        try:
            def _get():
                if self.exchange is None:
                    import ccxt

                    self.exchange = ccxt.binance()
                ticker = self.exchange.fetch_ticker('PAXG/USDT')
                return {
                    "indicator_id": "GOLD",
                    "timestamp": datetime.now(),
                    "value": float(ticker['last'])
                }

            return await run_external_io(_get)

        except Exception as e:
            logger.error(f"Failed to fetch Gold via PAXG: {e}")
            return None

    async def fetch_data(self):
        results = []
        gold = await self._fetch_gold_price()
        if gold:
            results.append(gold)
        return results

if __name__ == "__main__":
    async def main():
        p = CryptoGoldProvider()
        print(await p.fetch_data())
    asyncio.run(main())
