import httpx
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any
from .base_provider import BaseIndicatorProvider, logger
from config import settings

class OnchainProvider(BaseIndicatorProvider):
    """
    链上及矿工维度指标提供者
    拉取: Hashrate, Difficulty, Stablecoin Market Cap, Etc.
    """
    
    async def _fetch_mempool_data(self) -> List[Dict[str, Any]]:
        """从 Mempool.space拉取全网算力和挖矿难度"""
        results = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(settings.MEMPOOL_API_URL)
                if res.status_code == 200:
                    data = res.json()
                    # New API format: returns an object with currentHashrate and currentDifficulty
                    if isinstance(data, dict):
                        hr = data.get('currentHashrate')
                        diff = data.get('currentDifficulty')

                        # Get latest timestamp from hashrates array
                        dt = datetime.now()
                        if data.get('hashrates') and len(data['hashrates']) > 0:
                            last_point = data['hashrates'][-1]
                            dt = datetime.fromtimestamp(last_point.get('timestamp', datetime.now().timestamp()), tz=timezone.utc)

                        if hr:
                            results.append({
                                "indicator_id": "HASHRATE",
                                "timestamp": dt,
                                "value": hr
                            })
                        if diff:
                            results.append({
                                "indicator_id": "DIFFICULTY",
                                "timestamp": dt,
                                "value": diff
                            })
        except Exception as e:
            logger.error(f"Failed to fetch mempool data: {e}")

        return results

    async def _fetch_defillama_stablecoins(self) -> List[Dict[str, Any]]:
        """从 DefiLlama 拉取稳定币总市值及 USDT/USDC 分项"""
        results = []
        try:
            async with httpx.AsyncClient() as client:
                # 总市值
                res = await client.get(settings.STABLECOIN_CHART_API_URL)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list) and len(data) > 0:
                        last_point = data[-1]
                        val = last_point.get('totalCirculating', {}).get('peggedUSD')
                        if val:
                            results.append({
                                "indicator_id": "STABLECOIN_CAP",
                                "timestamp": datetime.now(),
                                "value": val
                            })

                # USDT/USDC 分项
                res2 = await client.get(settings.STABLECOIN_LIST_API_URL)
                if res2.status_code == 200:
                    coins = res2.json().get('peggedAssets', [])
                    for c in coins:
                        symbol = c.get('symbol', '')
                        if symbol == 'USDT':
                            val = c.get('circulating', {}).get('peggedUSD', 0)
                            if val:
                                results.append({
                                    "indicator_id": "USDT_CAP",
                                    "timestamp": datetime.now(),
                                    "value": val
                                })
                        elif symbol == 'USDC':
                            val = c.get('circulating', {}).get('peggedUSD', 0)
                            if val:
                                results.append({
                                    "indicator_id": "USDC_CAP",
                                    "timestamp": datetime.now(),
                                    "value": val
                                })
        except Exception as e:
            logger.error(f"Failed to fetch defillama data: {e}")
        return results

    async def fetch_data(self) -> List[Dict[str, Any]]:
        results = []
        
        # 算力, 难度, 稳定币市值
        tasks = [
            self._fetch_mempool_data(),
            self._fetch_defillama_stablecoins()
        ]
        
        res = await asyncio.gather(*tasks, return_exceptions=True)
        for r in res:
            if isinstance(r, list):
                results.extend(r)
                
        return results

if __name__ == "__main__":
    async def main():
        p = OnchainProvider()
        print(await p.fetch_data())
    asyncio.run(main())
