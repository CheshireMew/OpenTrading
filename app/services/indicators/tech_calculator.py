import httpx
import time
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from .base_provider import BaseIndicatorProvider, logger
from config import settings
from app.infra.executor import run_external_io
from app.services.market.ttl_cache import TtlMemoryCache

class TechCalculatorProvider(BaseIndicatorProvider):
    """
    技术面与逻辑测算指标提供者
    拉取/计算: 200WMA, S19/S21/S23_BREAKEVEN, BTC_DRAWDOWN
    数据源: Binance (via CCXT) + Mempool.space
    """

    def __init__(self):
        super().__init__()
        self._expensive_cache = TtlMemoryCache(
            settings.MARKET_EXPENSIVE_INDICATOR_TTL,
            copy_value=dict,
        )

    async def _calculate_200wma(self) -> Optional[Dict[str, Any]]:
        """计算比特币的 200 周移动平均线 (数据源: Binance CCXT)"""
        cached = self._expensive_cache.get("200wma")
        if cached is not None:
            return cached
        try:
            def _get():
                import ccxt

                exchange = ccxt.binance({'enableRateLimit': True})
                # 200周 ≈ 1400天，多拿一些确保够
                since = int((datetime.now() - timedelta(days=1500)).timestamp() * 1000)
                ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1w', since=since, limit=250)
                if not ohlcv or len(ohlcv) < 200:
                    logger.warning(f"200WMA: insufficient data, got {len(ohlcv) if ohlcv else 0} weeks")
                    return None

                closes = [x[4] for x in ohlcv]  # Close prices
                wma_200 = sum(closes[-200:]) / 200
                last_ts = ohlcv[-1][0] / 1000
                return {
                    "indicator_id": "200WMA",
                    "timestamp": datetime.fromtimestamp(last_ts, tz=timezone.utc),
                    "value": round(wma_200, 2)
                }
            result = await run_external_io(_get)
            if result is not None:
                self._expensive_cache.set("200wma", result)
            return result
        except Exception as e:
            logger.error(f"Failed to calculate 200WMA: {e}")
            return None

    async def _calculate_miner_breakeven(self) -> List[Dict[str, Any]]:
        """
        基于全网算力和难度计算主流矿机关机价
        计算 S19, S21, S23 三代矿机的关机价
        """
        results = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(settings.MEMPOOL_API_URL)
                if res.status_code == 200:
                    data = res.json()
                    diff = None
                    hr = None
                    dt = datetime.now()

                    # New API format: returns object with currentHashrate/currentDifficulty
                    if isinstance(data, dict):
                        diff = data.get('currentDifficulty')
                        hr = data.get('currentHashrate')
                        if data.get('hashrates') and len(data['hashrates']) > 0:
                            last_point = data['hashrates'][-1]
                            dt = datetime.fromtimestamp(last_point.get('timestamp', datetime.now().timestamp()), tz=timezone.utc)

                    if not diff or not hr:
                        return results

                    ELECTRICITY_COST_KWH = settings.MINING_ELECTRICITY_COST_KWH
                    BLOCK_REWARD = settings.BTC_BLOCK_REWARD

                    hr_th = hr / 1e12  # 全网 H/s -> TH/s
                    daily_btc = BLOCK_REWARD * settings.BTC_BLOCKS_PER_DAY  # 全网每日BTC产出
                    daily_btc_per_th = daily_btc / hr_th

                    # 矿机参数: (indicator_id, efficiency J/TH)
                    miners = [
                        ("S19_BREAKEVEN", settings.MINER_EFFICIENCY_JTH["S19 Pro"]),
                        ("S21_BREAKEVEN", settings.MINER_EFFICIENCY_JTH["S21"]),
                        ("S23_BREAKEVEN", settings.MINER_EFFICIENCY_JTH["S23"]),
                    ]

                    for ind_id, efficiency in miners:
                        daily_cost_per_th = efficiency / 1000.0 * 24 * ELECTRICITY_COST_KWH
                        breakeven = daily_cost_per_th / daily_btc_per_th if daily_btc_per_th > 0 else 0
                        results.append({
                            "indicator_id": ind_id,
                            "timestamp": dt,
                            "value": round(breakeven, 2)
                        })

        except Exception as e:
            logger.error(f"Failed to calculate miner breakeven: {e}")
        return results

    async def _calculate_drawdown(self) -> Optional[Dict[str, Any]]:
        """计算 BTC 距历史最高点的回撤幅度 (%) (数据源: Binance CCXT)"""
        cached = self._expensive_cache.get("drawdown")
        if cached is not None:
            return cached
        try:
            def _get():
                import ccxt

                exchange = ccxt.binance({'enableRateLimit': True})
                # Binance BTC/USDT 数据从 2017年8月开始
                all_data = []
                since = int(datetime(2017, 8, 1).timestamp() * 1000)  # Binance BTC/USDT start
                while True:
                    batch = exchange.fetch_ohlcv('BTC/USDT', '1d', since=since, limit=1000)
                    if not batch:
                        break
                    all_data.extend(batch)
                    since = batch[-1][0] + 1
                    if len(batch) < 1000:
                        break
                    time.sleep(exchange.rateLimit / 1000)

                if not all_data:
                    return None

                closes = [x[4] for x in all_data]
                ath = max(closes)
                current = closes[-1]
                drawdown = ((current - ath) / ath) * 100  # negative %
                last_ts = all_data[-1][0] / 1000
                return {
                    "indicator_id": "BTC_DRAWDOWN",
                    "timestamp": datetime.fromtimestamp(last_ts, tz=timezone.utc),
                    "value": round(drawdown, 2)
                }
            result = await run_external_io(_get)
            if result is not None:
                self._expensive_cache.set("drawdown", result)
            return result
        except Exception as e:
            logger.error(f"Failed to calculate BTC drawdown: {e}")
            return None

    async def fetch_data(self) -> List[Dict[str, Any]]:
        results = []
        tasks = [
            self._calculate_200wma(),
            self._calculate_miner_breakeven(),
            self._calculate_drawdown()
        ]

        res = await asyncio.gather(*tasks, return_exceptions=True)
        for r in res:
            if isinstance(r, dict):
                results.append(r)
            elif isinstance(r, list):
                results.extend(r)

        return results

if __name__ == "__main__":
    async def main():
        p = TechCalculatorProvider()
        data = await p.fetch_data()
        for d in data:
            print(f"{d['indicator_id']:15} | {d['timestamp']} | {d['value']}")
    asyncio.run(main())
