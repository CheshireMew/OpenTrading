from __future__ import annotations

import asyncio


async def check_all_sources() -> None:
    print("=" * 60)
    print("数据源可用性检查")
    print("=" * 60)

    print("\n[1/5] Checking FRED API...")
    try:
        from app.services.indicators.macro_provider_v2 import MacroProviderV2
        from config import settings

        if settings.FRED_API_KEY:
            provider = MacroProviderV2()
            data = await provider._fetch_fred_api("DGS10", "US10Y_CHECK")
            if data:
                print(f"[OK] FRED API working: {data['value']}")
            else:
                print("[ERROR] FRED API: no data returned")
        else:
            print("[WARN] FRED_API_KEY not configured")
    except Exception as exc:
        print(f"[ERROR] FRED API error: {exc}")

    print("\n[2/5] Checking YFinance...")
    try:
        from app.services.indicators.macro_provider_v2 import MacroProviderV2

        provider = MacroProviderV2()
        data = await provider._fetch_yfinance_ticker("^TNX", "US10Y_CHECK")
        if data:
            print(f"[OK] YFinance working: {data['value']}")
        else:
            print("[ERROR] YFinance: no data returned")
    except Exception as exc:
        print(f"[ERROR] YFinance error: {exc}")

    print("\n[3/5] Checking Binance PAXG...")
    try:
        from app.services.indicators.crypto_gold_provider import CryptoGoldProvider

        provider = CryptoGoldProvider()
        data = await provider._fetch_gold_price()
        if data:
            print(f"[OK] Binance PAXG working: ${data['value']}/oz")
        else:
            print("[ERROR] Binance PAXG: no data returned")
    except Exception as exc:
        print(f"[ERROR] Binance PAXG error: {exc}")

    print("\n[4/5] Checking Mempool.space...")
    try:
        from app.services.indicators.onchain_provider import OnchainProvider

        provider = OnchainProvider()
        data = await provider._fetch_mempool_data()
        if data:
            print(f"[OK] Mempool working: {len(data)} metrics")
            for item in data:
                print(f"  - {item['indicator_id']}: {item['value']}")
        else:
            print("[ERROR] Mempool: no data returned")
    except Exception as exc:
        print(f"[ERROR] Mempool error: {exc}")

    print("\n[5/5] Checking Fear & Greed Index...")
    try:
        from app.services.indicators.sentiment_provider import SentimentProvider

        provider = SentimentProvider()
        data = await provider._fetch_fear_greed_index()
        if data:
            print(f"[OK] Fear & Greed working: {data[0]['value']} (Index)")
        else:
            print("[ERROR] Fear & Greed: no data returned")
    except Exception as exc:
        print(f"[ERROR] Fear & Greed error: {exc}")

    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(check_all_sources())
