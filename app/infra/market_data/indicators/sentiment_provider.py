import httpx
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any
from .base_provider import BaseIndicatorProvider, logger
from config import settings
from app.infra.executor import run_external_io


class SentimentProvider(BaseIndicatorProvider):
    """
    市场情绪与资金动态指标提供者
    拉取: Fear&Greed Index, Google Trends 等
    """
    
    async def _fetch_fear_greed_index(self) -> List[Dict[str, Any]]:
        """从 Alternative.me 拉取恐惧与贪婪指数"""
        results = []
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{settings.SENTIMENT_API_URL}?limit=5")
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get('data', []):
                        val = int(item.get('value', 0))
                        ts = int(item.get('timestamp', 0))
                        if ts > 0:
                            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                            results.append({
                                "indicator_id": "FEAR_GREED",
                                "timestamp": dt,
                                "value": val
                            })
        except Exception as e:
            logger.error(f"Failed to fetch Fear & Greed Index: {e}")
        return results

    async def _fetch_google_trends(self) -> List[Dict[str, Any]]:
        """使用 pytrends 拉取 'buy bitcoin' 的搜索热度"""
        results = []
        try:
            def _get():
                from pytrends.request import TrendReq
                import pandas as pd

                pytrends = TrendReq(hl='en-US', tz=360)
                # kw_list = ["buy bitcoin"]
                pytrends.build_payload(["buy bitcoin"], cat=0, timeframe='now 7-d', geo='', gprop='')
                # pytrends fills its isPartial object column with False. Use
                # pandas' future behavior here; the numeric series is unchanged.
                with pd.option_context('future.no_silent_downcasting', True):
                    data = pytrends.interest_over_time()
                if not data.empty:
                    last_row = data.iloc[-1]
                    dt = last_row.name.to_pydatetime()
                    val = float(last_row['buy bitcoin'])
                    return {
                        "indicator_id": "GOOGLE_TRENDS_BTC",
                        "timestamp": dt,
                        "value": val
                    }
                return None
            res = await run_external_io(_get)
            if res:
                results.append(res)
        except Exception as e:
            logger.error(f"Failed to fetch Google Trends: {e}")
        return results

    async def fetch_data(self) -> List[Dict[str, Any]]:
        results = []
        tasks = [
            self._fetch_fear_greed_index(),
            self._fetch_google_trends()
        ]
        
        res = await asyncio.gather(*tasks, return_exceptions=True)
        for r in res:
            if isinstance(r, list):
                results.extend(r)
                
        return results

if __name__ == "__main__":
    async def main():
        p = SentimentProvider()
        print(await p.fetch_data())
    asyncio.run(main())
