from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from app.exceptions import NotFoundError
from app.infra.executor import run_database
from app.lifecycle import build_health_payload
from app.product import API_PREFIX
from app.runtime import RuntimeRole, runtime_role_has_target
from app.routers import config_router, market, research, tools
from config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"


def _resolve_frontend_asset(path: str) -> Path | None:
    if not FRONTEND_DIST_DIR.exists():
        return None

    candidate = (FRONTEND_DIST_DIR / path).resolve()
    frontend_root = FRONTEND_DIST_DIR.resolve()
    if frontend_root not in candidate.parents and candidate != frontend_root:
        return None
    if candidate.is_file():
        return candidate
    return None


def _frontend_not_ready_payload() -> dict[str, str]:
    return {
        "message": "Heimdall API is running",
        "docs": "/docs",
        "frontend_dev": f"http://127.0.0.1:{settings.FRONTEND_DEV_PORT}",
    }


async def root():
    if FRONTEND_INDEX_FILE.exists():
        return FileResponse(str(FRONTEND_INDEX_FILE))
    return _frontend_not_ready_payload()


async def health_check(request: Request):
    payload, status_code = await run_database(lambda: build_health_payload(request.app))
    return JSONResponse(status_code=status_code, content=payload)


async def liveness_check(request: Request):
    payload, status_code = build_health_payload(request.app, include_background=False)
    return JSONResponse(status_code=status_code, content=payload)


async def frontend_fallback(full_path: str):
    reserved_paths = {"api", "docs", "redoc", "openapi.json", "health"}
    if full_path in reserved_paths or any(full_path.startswith(f"{prefix}/") for prefix in reserved_paths):
        raise NotFoundError("Not found")

    if not FRONTEND_INDEX_FILE.exists():
        raise NotFoundError("Frontend build not found")

    asset = _resolve_frontend_asset(full_path)
    if asset:
        return FileResponse(str(asset))
    return FileResponse(str(FRONTEND_INDEX_FILE))


def register_app_routes(app: FastAPI, *, role: RuntimeRole) -> None:
    if runtime_role_has_target(role, "api"):
        app.include_router(market.router, prefix=API_PREFIX, tags=["市场数据"])
        app.include_router(tools.router, prefix=f"{API_PREFIX}/tools", tags=["工具"])
        app.include_router(research.router, prefix=API_PREFIX, tags=["研究追踪"])
        app.include_router(config_router.router, prefix=API_PREFIX, tags=["配置"])
    app.add_api_route("/", root, methods=["GET"], include_in_schema=False)
    app.add_api_route("/health", health_check, methods=["GET"])
    app.add_api_route("/health/live", liveness_check, methods=["GET"], include_in_schema=False)
    if runtime_role_has_target(role, "api"):
        app.add_api_route("/{full_path:path}", frontend_fallback, methods=["GET"], include_in_schema=False)
