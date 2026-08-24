from __future__ import annotations

import time

from app.runtime_builder import build_app_runtime_services
from app.runtime_refs import (
    INFRA_CACHE_SERVICE,
    INFRA_DATABASE_RUNTIME,
    MARKET_MARKET_DATA_SERVICE,
)


def check_redis_connection() -> None:
    runtime_services = build_app_runtime_services("api")
    cache_service = runtime_services.require_service(INFRA_CACHE_SERVICE)
    cache_service.connect()
    try:
        print("检查 Redis 连接...")
        if cache_service.client:
            print("[OK] Redis 连接成功")

            print("检查写入...")
            cache_service.set("check_key", "hello_redis", ttl=10)

            print("检查读取...")
            value = cache_service.get("check_key")
            print(f"   Value: {value}")

            if value == "hello_redis":
                print("[OK] 读写检查通过")
            else:
                print("[ERROR] 读写检查失败")
        else:
            print("[ERROR] Redis 连接失败 (client is None)")
    finally:
        database_runtime = runtime_services.get_service(INFRA_DATABASE_RUNTIME)
        if database_runtime is not None:
            database_runtime.dispose()


def check_market_cache() -> None:
    print("\n[DATA] 检查 K 线数据缓存...")
    runtime_services = build_app_runtime_services("api")
    provider = runtime_services.require_service(MARKET_MARKET_DATA_SERVICE)
    try:
        symbol = "BTC/USDT"

        start_time = time.time()
        print("   第 1 次请求 (应走交易所)...")
        first = provider.get_kline_data(symbol, limit=5)
        first_duration = time.time() - start_time
        print(f"   耗时: {first_duration:.4f}s")

        if not first:
            print("[ERROR] 获取数据失败，无法继续检查缓存")
            return

        start_time = time.time()
        print("   第 2 次请求 (应走 Redis)...")
        second = provider.get_kline_data(symbol, limit=5)
        second_duration = time.time() - start_time
        print(f"   耗时: {second_duration:.4f}s")

        if second_duration < first_duration and second_duration < 0.1:
            print("[OK] 缓存生效，速度显著提升")
        else:
            print("[WARN] 缓存似乎未生效，或网络极快")

        if first == second:
            print("[OK] 数据一致性检查通过")
        else:
            print("[ERROR] 数据不一致")
    finally:
        database_runtime = runtime_services.get_service(INFRA_DATABASE_RUNTIME)
        if database_runtime is not None:
            database_runtime.dispose()


if __name__ == "__main__":
    check_redis_connection()
    check_market_cache()
