from __future__ import annotations


APP_VERSION = "2.0.0"
API_PREFIX = "/api/v1"


def api_path(path: str) -> str:
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{API_PREFIX}{suffix}"


__all__ = ["APP_VERSION", "API_PREFIX", "api_path"]
