from __future__ import annotations

import asyncio

from app.services.indicators.macro_provider_v2 import MacroProviderV2 as MacroProvider


async def check_macro_provider() -> None:
    print("Checking MacroProvider...")
    provider = MacroProvider()
    data = await provider.fetch_data()
    print(f"Fetched {len(data)} indicators")
    for item in data:
        print(f"  {item['indicator_id']}: {item['value']}")


if __name__ == "__main__":
    asyncio.run(check_macro_provider())
