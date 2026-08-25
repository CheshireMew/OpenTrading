from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.routing import APIRoute

FrontendContractTarget = Literal["market", "tools", "config", "research"]

FRONTEND_CONTRACT_OPENAPI_KEY = "x-frontend-contract-target"


class FrontendContractRouter(APIRouter):
    def __init__(self, *args, frontend_contract_target: FrontendContractTarget, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.frontend_contract_target = frontend_contract_target

    def add_api_route(self, path: str, endpoint, *, openapi_extra=None, **kwargs) -> None:
        metadata = dict(openapi_extra or {})
        metadata[FRONTEND_CONTRACT_OPENAPI_KEY] = self.frontend_contract_target
        super().add_api_route(path, endpoint, openapi_extra=metadata, **kwargs)


def frontend_contract_target(route: APIRoute) -> FrontendContractTarget:
    target = (route.openapi_extra or {}).get(FRONTEND_CONTRACT_OPENAPI_KEY)
    if target in {"market", "tools", "config", "research"}:
        return target
    raise RuntimeError(f"API route has no frontend contract target: {route.name} {route.path}")


def frontend_contract_filename(target: FrontendContractTarget) -> str:
    return f"{target}.ts"
