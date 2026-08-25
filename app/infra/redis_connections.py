from __future__ import annotations

import time
from typing import Any

try:
    import redis
    import redis.asyncio as async_redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
except ModuleNotFoundError:
    redis = None
    async_redis = None
    NoBackoff = None
    Retry = None

from utils.logger import logger


class RedisConnections:
    def __init__(self, app_settings: Any) -> None:
        self.settings = app_settings
        self.client = None
        self.async_client = None
        self._last_connection_attempt = 0.0
        self._last_async_connection_attempt = 0.0
        self.available = redis is not None

    def _connection_kwargs(self) -> dict[str, Any]:
        host = str(self.settings.REDIS_HOST).strip()
        if host.lower() == "localhost":
            host = "127.0.0.1"
        options = {
            "host": host,
            "port": self.settings.REDIS_PORT,
            "db": self.settings.REDIS_DB,
            "password": self.settings.REDIS_PASSWORD or None,
            "decode_responses": True,
            "socket_connect_timeout": max(float(self.settings.REDIS_CONNECT_TIMEOUT), 0.05),
            "socket_timeout": max(float(self.settings.REDIS_SOCKET_TIMEOUT), 0.05),
            "retry_on_error": [],
            "health_check_interval": 30,
        }
        if Retry is not None and NoBackoff is not None:
            options["retry"] = Retry(NoBackoff(), 0)
        return options

    def _may_retry(self, last_attempt: float, *, force: bool) -> bool:
        return force or last_attempt <= 0 or (
            time.monotonic() - last_attempt >= max(float(self.settings.REDIS_RETRY_INTERVAL), 1.0)
        )

    def connect(self, *, force: bool = False) -> None:
        if redis is None:
            return
        if self.client is not None or not self._may_retry(self._last_connection_attempt, force=force):
            return
        self._last_connection_attempt = time.monotonic()
        client = None
        try:
            pool = redis.ConnectionPool(**self._connection_kwargs())
            client = redis.Redis(connection_pool=pool)
            client.ping()
            self.client = client
            logger.info("[OK] Redis 连接成功")
        except Exception as exc:
            logger.warning(f"Redis 连接失败 (将降级运行): {exc}")
            if client is not None:
                client.connection_pool.disconnect()

    async def connect_async(self, *, force: bool = False) -> None:
        if async_redis is None:
            return
        if self.async_client is not None or not self._may_retry(self._last_async_connection_attempt, force=force):
            return
        self._last_async_connection_attempt = time.monotonic()
        client = async_redis.Redis(**self._connection_kwargs())
        try:
            await client.ping()
            self.async_client = client
            logger.info("[OK] Redis 异步连接成功")
        except Exception as exc:
            logger.warning(f"Redis 异步连接失败 (将降级运行): {exc}")
            await client.aclose()

    def ensure_sync(self) -> bool:
        if self.client is None:
            self.connect()
        return self.client is not None

    async def ensure_async(self) -> bool:
        if self.async_client is None:
            await self.connect_async()
        return self.async_client is not None

    def discard_sync(self) -> None:
        client = self.client
        self.client = None
        if client is not None:
            client.connection_pool.disconnect()

    async def discard_async(self) -> None:
        client = self.async_client
        self.async_client = None
        if client is not None:
            await client.aclose()

    async def close(self) -> None:
        await self.discard_async()
        self.discard_sync()


__all__ = ["RedisConnections"]
