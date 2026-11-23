"""
工具类 API 路由
"""
from __future__ import annotations

from fastapi import Depends, Request

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_tools_app_service
from app.rate_limit import limiter
from app.contracts.dto.tools import (
    DCAResponse,
    PairCompareToolResponse,
    ToolsPageContractResponse,
)
from app.contracts.tools import ComparePairsCommand, DCA_MAX_DAYS, DCA_STRATEGY_KEYS, SimulateDcaCommand
from config import settings


router = FrontendContractRouter(frontend_contract_target="tools")


@router.get("/contract", response_model=ToolsPageContractResponse)
async def get_tools_contract():
    return ToolsPageContractResponse(
        dca_defaults=SimulateDcaCommand.model_validate({}),
        dca_strategies=list(DCA_STRATEGY_KEYS),
        dca_multiplier_default=settings.DCA_DEFAULT_MULTIPLIER,
        dca_max_days=DCA_MAX_DAYS,
        compare_defaults=ComparePairsCommand.model_validate({}),
    )


@router.post("/dca_simulate", response_model=DCAResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def dca_simulate(
    request: Request,
    body: SimulateDcaCommand,
    service = Depends(get_tools_app_service),
):
    return await service.simulate_dca(body)


@router.post("/compare_pairs", response_model=PairCompareToolResponse)
@limiter.limit(settings.RATE_LIMIT_HEAVY)
async def compare_pairs(
    request: Request,
    body: ComparePairsCommand,
    service = Depends(get_tools_app_service),
):
    return await service.compare_pairs(body)
