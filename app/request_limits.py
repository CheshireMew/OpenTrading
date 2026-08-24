from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import re
from typing import Any

from fastapi.responses import JSONResponse


AsgiReceive = Callable[[], Awaitable[dict[str, Any]]]
AsgiSend = Callable[[dict[str, Any]], Awaitable[None]]


class RequestBodyLimitMiddleware:
    """Buffer and bound request bodies for the small set of import endpoints."""

    def __init__(self, app, *, route_limits: Mapping[tuple[str, str], int]) -> None:
        self._app = app
        self._route_limits = {
            (method.upper(), path): int(limit)
            for (method, path), limit in route_limits.items()
        }
        self._template_limits = [
            (
                method,
                re.compile(
                    "^"
                    + "/".join(
                        "[^/]+"
                        if segment.startswith("{") and segment.endswith("}")
                        else re.escape(segment)
                        for segment in path.split("/")
                    )
                    + "$"
                ),
                limit,
            )
            for (method, path), limit in self._route_limits.items()
            if "{" in path
        ]

    async def __call__(self, scope, receive: AsgiReceive, send: AsgiSend) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        key = (str(scope.get("method", "")).upper(), str(scope.get("path", "")))
        limit = self._route_limits.get(key)
        if limit is None:
            limit = next(
                (
                    candidate_limit
                    for candidate_method, pattern, candidate_limit in self._template_limits
                    if candidate_method == key[0] and pattern.fullmatch(key[1])
                ),
                None,
            )
        if limit is None:
            await self._app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > limit:
            await self._reject(scope, receive, send, limit)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                await self._reject(scope, receive, send, limit)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self._app(scope, replay_receive, send)

    @staticmethod
    def _content_length(scope) -> int | None:
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() != b"content-length":
                continue
            try:
                return int(raw_value)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    async def _reject(scope, receive: AsgiReceive, send: AsgiSend, limit: int) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds the {limit} byte limit"},
        )
        await response(scope, receive, send)
