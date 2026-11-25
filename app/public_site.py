"""The public website serves market data, never the local application's records."""
import asyncio
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from config import settings


PUBLIC_COMPUTATIONS = {"dca_simulate", "compare_pairs", "evaluate_browser_screener"}
PUBLIC_READS = {"get_config", "get_currencies", "get_tools_contract", "workspace_defaults", "chart_symbols", "chart_symbol_icon", "chart_bars", "chart_replay_bars", "chart_quotes", "chart_capabilities", "chart_stream", "get_asset_research"}


def public_route(route):
    name = getattr(route, "name", "")
    endpoint = getattr(route, "endpoint", None)
    module = getattr(endpoint, "__module__", "")
    market_read = module.startswith("app.routers.market.") and "GET" in (getattr(route, "methods", None) or ()) and name != "signal_lab_inventory"
    market_stream = module == "app.routers.market.realtime" and name == "websocket_realtime"
    return market_read or market_stream or name in PUBLIC_READS | PUBLIC_COMPUTATIONS


class PublicRequestMiddleware:
    def __init__(self, app):
        self.app = app
        self.computations = asyncio.Semaphore(1)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if scope["type"] == "websocket":
            origin = headers.get(b"origin", b"").decode("latin-1")
            parsed = urlsplit(origin)
            if parsed.scheme != "https" or parsed.netloc != settings.PUBLIC_HOST:
                return await send({"type": "websocket.close", "code": 1008})
        else:
            # Bound the actual stream too: Content-Length alone does not cover
            # chunked requests. Buffer only the small computation payloads.
            maximum = 64 * 1024
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > maximum or len(scope.get("query_string", b"")) > 8192:
                    return await JSONResponse({"detail": "Request too large"}, status_code=413)(scope, receive, send)
                if not message.get("more_body"):
                    break
            consumed = False
            original_receive = receive

            async def bounded_receive():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = bounded_receive
        heavy_paths = {"/api/v1/tools/dca_simulate", "/api/v1/tools/compare_pairs", "/api/v1/research/screener-preview"}
        if scope["type"] == "http" and scope.get("method") == "POST" and scope["path"] in heavy_paths:
            if self.computations.locked():
                return await JSONResponse({"detail": "A computation is running; retry shortly"}, status_code=429)(scope, receive, send)
            async with self.computations:
                return await self.app(scope, receive, send)
        return await self.app(scope, receive, send)
