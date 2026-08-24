from __future__ import annotations

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv


async def check_fred_api() -> bool:
    print("=" * 70)
    print("          FRED API Configuration Check")
    print("=" * 70)
    print()

    load_dotenv()
    api_key = os.getenv("FRED_API_KEY")

    if not api_key:
        print("[ERROR] FRED_API_KEY not found in .env file")
        return False

    print(f"[OK] API Key loaded: {api_key[:8]}...{api_key[-4:]}")
    print()
    print("Checking FRED API connection...")
    print()

    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        checks = [
            ("DGS10", "10-Year Treasury Rate"),
            ("DFF", "Federal Funds Rate"),
            ("M2SL", "M2 Money Supply"),
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            for series_id, name in checks:
                params = {
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "limit": 1,
                    "sort_order": "desc",
                }

                response = await client.get(url, params=params)

                if response.status_code != 200:
                    print(f"[FAIL] {name:25} : HTTP {response.status_code}")
                    print(f"       Error: {response.text[:100]}")
                    return False

                data = response.json()
                observations = data.get("observations", [])
                if not observations:
                    print(f"[FAIL] {name:25} : No data returned")
                    continue

                value = observations[0].get("value")
                date = observations[0].get("date")
                if value != ".":
                    print(f"[OK] {name:25} : {value:>10} ({date})")
                else:
                    print(f"[--] {name:25} : No data ({date})")

                await asyncio.sleep(0.5)

        print()
        print("=" * 70)
        print("SUCCESS: FRED API is configured and reachable.")
        print("=" * 70)
        return True
    except Exception as exc:
        print(f"[FAIL] Check failed: {exc}")
        print()
        print("Please check:")
        print("  1. API Key is correct")
        print("  2. Network connection is available")
        print("  3. Firewall is not blocking FRED API")
        return False


if __name__ == "__main__":
    success = asyncio.run(check_fred_api())
    sys.exit(0 if success else 1)
