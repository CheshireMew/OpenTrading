from __future__ import annotations

import asyncio

from app.services.indicators.onchain_provider import OnchainProvider


async def check_onchain_provider() -> None:
    print("Checking OnchainProvider...")
    provider = OnchainProvider()
    data = await provider.fetch_data()
    print(f"Fetched {len(data)} indicators:")
    for item in data:
        print(f"  {item['indicator_id']}: {item['value']}")


if __name__ == "__main__":
    asyncio.run(check_onchain_provider())
