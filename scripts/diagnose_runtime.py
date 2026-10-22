from __future__ import annotations

import argparse
import asyncio

from app.runtime import build_app_runtime_services


async def check_external_sources() -> None:
    print("\nExternal data sources")

    from app.services.indicators.onchain_provider import OnchainProvider
    from app.services.indicators.sentiment_provider import SentimentProvider

    checks = [
        ("Mempool.space", lambda: OnchainProvider()._fetch_mempool_data()),
        ("Fear & Greed", lambda: SentimentProvider()._fetch_fear_greed_index()),
    ]

    for label, factory in checks:
        try:
            task = factory()
            if task is None:
                print(f"  [skip] {label}: missing config")
                continue
            result = await task
            status = "ok" if result else "empty"
            print(f"  [{status}] {label}")
        except Exception as exc:
            print(f"  [fail] {label}: {exc}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose OpenTrading runtime dependencies.")
    parser.add_argument("--external", action="store_true", help="also call public market data APIs")
    args = parser.parse_args()

    services = build_app_runtime_services("api")
    try:
        print("Runtime")
        api = services.require_api()
        print(f"  database: {services.infra.database_runtime.engine.dialect.name} ({services.infra.database_runtime.source})")
        print(f"  cache: {type(services.infra.cache_service).__name__}")
        print(f"  market query: {type(api.market.query).__name__}")
        print(f"  tools: {type(api.tools.app).__name__}")
        if args.external:
            await check_external_sources()
    finally:
        services.dispose()


if __name__ == "__main__":
    asyncio.run(main())
