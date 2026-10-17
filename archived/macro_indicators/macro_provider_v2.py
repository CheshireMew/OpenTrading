"""
宏观经济指标提供者 V2 - 多数据源版本
优先使用 FRED API（稳定可靠），降级到 YFinance
"""
import requests as req_sync
from datetime import datetime, timedelta
import asyncio
from typing import List, Dict, Any, Optional
from .base_provider import BaseIndicatorProvider, logger
from config import settings
from app.domain.market.indicator_catalog import MACRO_INDICATOR_SOURCES
from app.infra.executor import run_database, run_external_io
from app.services.fred_api_config_service import read_fred_api_key


class MacroProviderV2(BaseIndicatorProvider):
    """
    宏观经济指标提供者（多源版本）
    数据源优先级：
    1. FRED API (官方数据，最稳定)
    2. YFinance (fallback)
    """

    def __init__(self, latest_timestamp_reader=None):
        super().__init__()
        self._latest_timestamp_reader = latest_timestamp_reader
        self._latest_timestamps: dict[str, datetime] = {}

    async def _fetch_fred_api(self, series_id: str, indicator_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        从 FRED 官方 API 获取数据（使用 sync requests 在线程池中执行，避免 httpx async TLS 问题）
        """
        fred_api_key = await run_external_io(read_fred_api_key)
        if not fred_api_key:
            logger.warning("FRED_API_KEY not configured, skipping FRED source")
            return None

        def _get():
            url = settings.FRED_API_URL
            params = {
                'series_id': series_id,
                'api_key': fred_api_key,
                'file_type': 'json',
                'sort_order': 'desc',
                'limit': 3650
            }
            latest_timestamp = self._latest_timestamps.get(indicator_id)
            if latest_timestamp is not None:
                observation_start = latest_timestamp - timedelta(
                    days=max(int(settings.MARKET_INDICATOR_OVERLAP_DAYS), 1)
                )
                params['observation_start'] = observation_start.strftime('%Y-%m-%d')
            res = req_sync.get(url, params=params, timeout=settings.FRED_REQUEST_TIMEOUT)
            if res.status_code == 200:
                data = res.json()
                observations = data.get('observations', [])
                points = []
                for latest in observations:
                    value_str = latest.get('value')
                    if value_str == '.' or not value_str:
                        continue
                    points.append(
                        {
                            "indicator_id": indicator_id,
                            "timestamp": datetime.strptime(latest['date'], '%Y-%m-%d'),
                            "value": float(value_str)
                        }
                    )
                return list(reversed(points)) if points else None
            return None

        try:
            return await run_external_io(_get)
        except Exception as e:
            logger.error(f"Failed to fetch FRED {series_id}: {e}")

        return None

    async def _fetch_yfinance_ticker(self, ticker: str, indicator_id: str) -> Optional[Dict[str, Any]]:
        """从 Yahoo Finance 拉取（降级备用）"""
        try:
            def _get():
                import yfinance as yf

                # 不传 session，让 yfinance 自动使用 curl_cffi
                tkr = yf.Ticker(ticker)
                hist = tkr.history(period="5d")
                if hist.empty:
                    return None
                last_row = hist.iloc[-1]
                dt = last_row.name.to_pydatetime()
                val = float(last_row['Close'])
                return {
                    "indicator_id": indicator_id,
                    "timestamp": dt,
                    "value": val
                }

            return await run_external_io(_get)

        except Exception as e:
            logger.error(f"Failed to fetch YFinance {ticker}: {e}")
            return None

    async def _get_indicator_with_fallback(self,
                                          fred_id: Optional[str],
                                          yf_ticker: str | None,
                                          indicator_id: str) -> List[Dict[str, Any]]:
        """
        多源降级获取
        优先 FRED -> 降级 YFinance
        """
        # 尝试 FRED
        if fred_id:
            result = await self._fetch_fred_api(fred_id, indicator_id)
            if result:
                logger.info(f"[OK] {indicator_id} from FRED")
                return result

        if not yf_ticker:
            return []

        # 降级到 YFinance
        logger.info(f"[FALLBACK] {indicator_id} fallback to YFinance")
        await asyncio.sleep(settings.YFINANCE_REQUEST_DELAY)  # 限流延迟
        result = await self._fetch_yfinance_ticker(yf_ticker, indicator_id)
        if result:
            logger.info(f"[OK] {indicator_id} from YFinance")
            return [result]
        return []

    async def fetch_data(self) -> List[Dict[str, Any]]:
        if self._latest_timestamp_reader is not None:
            indicator_ids = [source.indicator_id for source in MACRO_INDICATOR_SOURCES]
            self._latest_timestamps = await run_database(
                lambda: self._latest_timestamp_reader(indicator_ids)
            )

        semaphore = asyncio.Semaphore(3)

        async def fetch_source(source):
            async with semaphore:
                return await self._get_indicator_with_fallback(
                    source.fred_id,
                    source.yf_ticker,
                    source.indicator_id,
                )

        batches = await asyncio.gather(
            *(fetch_source(source) for source in MACRO_INDICATOR_SOURCES)
        )
        return [point for batch in batches for point in batch]

if __name__ == "__main__":
    async def main():
        p = MacroProviderV2()
        data = await p.fetch_data()
        for d in data:
            print(f"{d['indicator_id']:15} | {d['timestamp']} | {d['value']}")
    asyncio.run(main())
