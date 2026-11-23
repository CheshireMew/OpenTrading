from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import HTTPException, Query, Request, Response

from app.contracts.dto.signal_lab import (
    SignalLabInventoryResponse,
    SignalLabLiquidityResponse,
    SignalLabPriceResponse,
    SignalLabRefreshRequest,
    SignalLabRefreshResponse,
)
from app.contracts.frontend import FrontendContractRouter
from app.infra.executor import run_database, run_external_io
from signal_lab.structured_data import dumps_json


router = FrontendContractRouter(
    frontend_contract_target="market", prefix="/signal-lab", tags=["宏观与历史数据"],
)
Days = Annotated[int, Query(ge=30, le=3650)]
ChangeDays = Annotated[int, Query(ge=1, le=365)]
PriceBasis = Literal["raw", "adjusted"]


async def _run(request: Request, action, *, executor=run_database):
    runtime = request.app.state.runtime_services.infra.signal_lab
    if runtime is None:
        raise HTTPException(status_code=503, detail="Signal Lab runtime unavailable")

    def invoke():
        with runtime.bind():
            return action(runtime.views)

    try:
        return await executor(invoke)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _json(payload, *, request_id: str | None = None) -> Response:
    return Response(
        dumps_json(payload).encode("utf-8"),
        media_type="application/json",
        headers={"Cache-Control": "no-store", "X-Request-ID": request_id or uuid4().hex},
    )


@router.get("/liquidity", response_model=SignalLabLiquidityResponse)
async def signal_lab_liquidity(request: Request, days: Days = 365, change_days: ChangeDays = 30):
    data = await _run(request, lambda views: views.liquidity.liquidity(days=days, change_days=change_days))
    return _json(data)


@router.get("/database", response_model=SignalLabInventoryResponse)
async def signal_lab_inventory(request: Request):
    data = await _run(request, lambda views: views.workbench.database_status())
    return _json(data)


@router.get("/prices/history", response_model=SignalLabPriceResponse)
async def signal_lab_price_history(
    request: Request, instrument: str, start: date, end: date,
    basis: PriceBasis = "raw", snapshot: str | None = None,
    limit: Annotated[int, Query(ge=100, le=5000)] = 5000,
):
    data = await _run(request, lambda views: views.prices.history(
        instrument, start=start, end=end, basis=basis, limit=limit, snapshot_hash=snapshot,
    ))
    return _json(data)


@router.get("/prices/download", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
async def signal_lab_price_download(
    request: Request, instrument: str, start: date, end: date,
    basis: PriceBasis = "raw", snapshot: str | None = None,
):
    payload, filename = await _run(request, lambda views: views.prices.download(
        instrument, start=start, end=end, basis=basis, snapshot_hash=snapshot,
    ))
    return Response(payload, media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-cache",
        "X-Request-ID": uuid4().hex,
    })


@router.post("/liquidity/refresh", response_model=SignalLabRefreshResponse)
async def refresh_signal_lab_liquidity(request: Request, body: SignalLabRefreshRequest | None = None):
    request_id = uuid4().hex
    try:
        result = await _run(
            request, lambda views: views.liquidity.refresh(request_id=request_id), executor=run_external_io,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc), headers={"X-Request-ID": request_id}) from exc
    return _json(result, request_id=request_id)
