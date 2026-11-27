import httpx
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from .base_provider import BaseIndicatorProvider, logger
from config import settings
from app.infra.executor import run_external_io
from app.infra.ttl_cache import TtlMemoryCache
from app.infra.market_data.exchange import ExchangeGateway
from app.domain.market.candles import candle_end_ms

class TechCalculatorProvider(BaseIndicatorProvider):
    """
    技术面与逻辑测算指标提供者
    拉取/计算: 200WMA, S19/S21/S23_BREAKEVEN, BTC_DRAWDOWN
    数据源: Binance 公共 REST API + Mempool.space
    """

    def __init__(self):
        super().__init__()
        self._expensive_cache = TtlMemoryCache(
            settings.MARKET_EXPENSIVE_INDICATOR_TTL,
            copy_value=dict,
        )
        self._drawdown_peak = 0.0
        self._drawdown_since = int(datetime(2017, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)

    async def _calculate_200wma(self) -> Optional[Dict[str, Any]]:
        """计算比特币的 200 周移动平均线。"""
        cached = self._expensive_cache.get("200wma")
        if cached is not None:
            return cached
        try:
            def _get():
                # 200周 ≈ 1400天，多拿一些确保够
                since = int((datetime.now(timezone.utc) - timedelta(days=1500)).timestamp() * 1000)
                with ExchangeGateway("binance") as exchange:
                    ohlcv, _ = exchange.fetch_ohlcv('BTC/USDT', '1w', since=since, limit=250)
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
                    dt = datetime.now(timezone.utc)

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
        """计算 BTC 日线收盘价距历史最高收盘价的回撤幅度。"""
        cached = self._expensive_cache.get("drawdown")
        if cached is not None:
            return cached
        try:
            def _get():
                # Keep a scalar maximum for completed days. Refresh the open day
                # each time; an intraday close must not become a permanent ATH.
                peak, since = self._drawdown_peak, self._drawdown_since
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                current = last_ts = None
                checkpoint = since
                with ExchangeGateway("binance") as exchange:
                    while since <= now_ms:
                        batch, _ = exchange.fetch_ohlcv('BTC/USDT', '1d', since=since, limit=exchange.fetch_limit)
                        if not batch:
                            break
                        for row in batch:
                            current, last_ts = row[4], int(row[0])
                            if candle_end_ms(last_ts, "1d") <= now_ms:
                                peak = max(peak, current)
                                checkpoint = candle_end_ms(last_ts, "1d")
                        following = int(batch[-1][0]) + 1
                        if following <= since:
                            raise ValueError("BTC 历史分页未向前推进")
                        since = following
                        if len(batch) < exchange.fetch_limit:
                            break

                if current is None or last_ts is None:
                    return None
                self._drawdown_peak, self._drawdown_since = peak, checkpoint
                ath = max(peak, current)
                drawdown = ((current - ath) / ath) * 100  # negative %
                return {
                    "indicator_id": "BTC_DRAWDOWN",
                    "timestamp": datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc),
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
