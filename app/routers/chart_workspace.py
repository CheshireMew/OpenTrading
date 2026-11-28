from __future__ import annotations

import asyncio
import time
from typing import Literal
from fastapi import Depends, HTTPException, Path, Query, Request, Response, WebSocket, WebSocketDisconnect
from starlette.requests import HTTPConnection
from app.contracts.frontend import FrontendContractRouter
from app.contracts.chart_workspace import (ChartSymbol, ChartBars, ChartQuote, WorkspaceDocument, WorkspaceWrite,
    PineRun, PineRunRequest, PineRecords, PineCapabilities)
from app.infra.executor import run_workspace
from app.infra.market_data.chart import MarketHttpError
from app.infra.market_data.exchange import MarketDataError
from app.infra.persistence.chart_workspace_repository import WorkspaceConflict
from app.services.chart_workspace_runs import PineCapacityError

router = FrontendContractRouter(frontend_contract_target="chartWorkspace",prefix="/chart-workspace",tags=["图表工作台"])
Kind = Literal["layouts","watchlists","scripts"]


@router.get("/defaults/{kind}", response_model=list[WorkspaceDocument])
async def workspace_defaults(kind: Kind):
    from app.services.chart_workspace_seed import default_documents
    return default_documents(kind)


async def services(connection: HTTPConnection):
    runtime = connection.app.state.runtime_services.require_api().chart_workspace
    if runtime is None or runtime.closed:
        raise HTTPException(503, "图表工作台尚未就绪")
    return runtime


def document_error(exc):
    if isinstance(exc, KeyError):
        return HTTPException(404, "记录不存在")
    if isinstance(exc, WorkspaceConflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, PineCapacityError):
        return HTTPException(429, str(exc))
    return HTTPException(422, str(exc))


def document_call(fn):
    try:
        return fn()
    except (KeyError, ValueError) as exc:
        raise document_error(exc) from exc


@router.get("/symbols",response_model=list[ChartSymbol])
async def chart_symbols(symbol: str | None = Query(default=None, max_length=160), wait: bool = False, service=Depends(services)):
    if symbol is not None:
        try:
            await service.market.resolve(symbol)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return await service.market.symbols(wait_for_refresh=wait)


@router.get("/symbols/search", response_model=list[ChartSymbol])
async def search_chart_symbols(query: str = Query(min_length=1, max_length=128), service=Depends(services)):
    try:
        return await service.market.search_symbols(query)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/symbol-icons/{asset}", response_class=Response,
            responses={200: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}, "image/gif": {}}}})
async def chart_symbol_icon(request: Request, asset: str = Path(pattern=r"^[A-Z0-9._-]{1,40}$"), service=Depends(services)):
    icon = await service.market.icons.get(asset)
    if icon is None:
        return Response(status_code=404, headers={"Cache-Control": "public, max-age=60"})
    headers = {"Cache-Control": "public, max-age=86400, stale-if-error=604800", "ETag": icon.etag,
               "X-Content-Type-Options": "nosniff"}
    if request.headers.get("if-none-match") == icon.etag:
        return Response(status_code=304, headers=headers)
    return Response(icon.content, media_type=icon.media_type, headers=headers)


@router.get("/bars",response_model=ChartBars)
async def chart_bars(symbol:str,timeframe:str,limit:int=Query(1000,ge=1,le=1000),start:int|None=None,end:int|None=None,service=Depends(services)):
    try:
        return await service.market.bars(symbol,timeframe,limit,start,end)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    except (MarketHttpError, MarketDataError, TimeoutError) as exc:
        raise HTTPException(502, "历史行情暂时加载失败，请重试") from exc


@router.get("/quotes",response_model=list[ChartQuote])
async def chart_quotes(symbols:str,service=Depends(services)):
    return await service.market.quotes(list(dict.fromkeys(symbols.split(',')))[:100])


@router.get("/replay/bars", response_model=ChartBars)
async def chart_replay_bars(response: Response, symbol: str, timeframe: str,
                            end: int = Query(...), start: int | None = Query(None),
                            limit: int = Query(1000, ge=1, le=1000), service=Depends(services)):
    upper = min(end, int(time.time() * 1000))
    if start is not None and start >= upper:
        raise HTTPException(422, "回放开始时间必须早于结束时间")
    try:
        result = await service.market.replay_bars(symbol, timeframe, limit, start, upper)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (MarketHttpError, MarketDataError, TimeoutError) as exc:
        raise HTTPException(502, "回放历史行情暂时加载失败，请重试") from exc
    response.headers["Cache-Control"] = "public, max-age=" + (
        "86400" if result.bars and end == upper and upper < int(time.time() * 1000) - 86400000 else "30")
    return result


@router.get("/capabilities",response_model=PineCapabilities)
async def chart_capabilities():
    return PineCapabilities(supported=["Pine v5/v6 常用指标与 strategy", "多图、绘图、原版 v7.2", "已接入品种的多周期请求"],
        limited=["varip 支持全局标量（OpenTrading 兼容层），不支持局部变量和集合", "实时计算使用实际收到的行情更新", "历史 OHLC 成交模拟不是逐 tick 还原", "USD/USDT 采用报价数值记账，不执行汇率换算"],
        unsupported=["OCA 联动", "强平价格与跨币种换算", "财报与经济数据", "未接入的外部 Pine 库（已内置 DevLucem/ZigLib/1）", "lookahead_on", "Bar Magnifier"])


@router.get("/pine-runs",response_model=list[PineRun])
async def chart_pine_runs(service=Depends(services)):
    return await run_workspace(service.runs.list)


@router.post("/pine-runs",response_model=PineRun)
async def chart_create_pine_run(body:PineRunRequest,request:Request,service=Depends(services)):
    try:
        return await service.runs.create(body,str(request.base_url).rstrip('/')+'/api/v1/chart-workspace',recording="report")
    except (KeyError, ValueError) as exc:
        raise document_error(exc) from exc


@router.get("/pine-runs/{key}",response_model=PineRun)
async def chart_get_pine_run(key:str,service=Depends(services)):
    return await run_workspace(lambda: document_call(lambda:service.runs.get(key)))


@router.post("/pine-runs/{key}/cancel",response_model=PineRun)
async def chart_cancel_pine_run(key:str,service=Depends(services)):
    await run_workspace(lambda: document_call(lambda:service.runs.get(key)))
    return await service.runs.cancel(key)


@router.post("/pine-runs/{key}/rerun",response_model=PineRun)
async def chart_rerun_pine(key:str,request:Request,service=Depends(services)):
    previous = await run_workspace(lambda: document_call(lambda:service.runs.get(key)))
    try:
        return await service.runs.create(previous.request,str(request.base_url).rstrip('/')+'/api/v1/chart-workspace',frozen_from=key)
    except (KeyError, ValueError) as exc:
        raise document_error(exc) from exc


@router.get("/pine-runs/{key}/records",response_model=PineRecords)
async def chart_pine_records(key:str,kind:Literal["equity","trades","open_trades","orders","fills","warnings","bars"]="trades",
        offset:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=10000),sampled:bool=False,service=Depends(services)):
    return await run_workspace(lambda: document_call(lambda:service.runs.records(key,kind,offset,limit,sampled=sampled)))


@router.get("/{kind}",response_model=list[WorkspaceDocument])
async def chart_documents(kind:Kind,service=Depends(services)):
    return await run_workspace(lambda: service.store.list(kind))


@router.get("/{kind}/{key}",response_model=WorkspaceDocument)
async def chart_document(kind:Kind,key:str,version:int|None=None,service=Depends(services)):
    return await run_workspace(lambda: document_call(lambda:service.store.get(kind,key,version)))


@router.put("/{kind}/{key}",response_model=WorkspaceDocument)
async def chart_save_document(kind:Kind,key:str,body:WorkspaceWrite,service=Depends(services)):
    return await run_workspace(lambda: document_call(lambda:service.store.put(kind,key,body)))


@router.post("/{kind}/{key}/archive",response_model=dict[str,bool])
async def chart_archive_document(kind:Kind,key:str,service=Depends(services)):
    await run_workspace(lambda: document_call(lambda:service.store.archive(kind,key)))
    return {"archived":True}


@router.websocket("/stream")
async def chart_stream(websocket:WebSocket):
    service = await services(websocket)
    await websocket.accept()
    queue = asyncio.Queue(maxsize=2000)
    subscriptions = {}
    class Subscriber:
        def __init__(self, generation): self.generation = generation
        def put_nowait(self, item): queue.put_nowait({**item,"generation":self.generation})
        def full(self): return queue.full()
        def get_nowait(self): return queue.get_nowait()
    async def sender():
        while True:
            item = await queue.get()
            current = subscriptions.get((item["symbol"],item["timeframe"]))
            if current and item.get("generation") == current.generation:
                await websocket.send_json(item)
    task = asyncio.create_task(sender())
    try:
        while True:
            message = await websocket.receive_json()
            key,tf = str(message.get("symbol","")),str(message.get("timeframe",""))
            if message.get("type") == "subscribe":
                from config import settings
                if len(subscriptions)>=(8 if settings.PUBLIC_SITE else 32) and (key, tf) not in subscriptions:
                    continue
                try:
                    info = await service.market.resolve(key)
                    if tf not in info.timeframes:
                        raise ValueError("该品种不支持此周期")
                    previous = subscriptions.get((key,tf))
                    if previous:
                        service.market.unsubscribe(key,tf,previous)
                    listener = Subscriber(message.get("generation",0))
                    subscriptions[(key,tf)] = listener
                    service.market.subscribe(key,tf,listener)
                except ValueError as exc:
                    await websocket.send_json({"type":"status","symbol":key,"timeframe":tf,"status":"error","error":str(exc),"generation":message.get("generation",0)})
            elif message.get("type") == "unsubscribe":
                listener = subscriptions.pop((key,tf),None)
                if listener:
                    service.market.unsubscribe(key,tf,listener)
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        for (key,tf),listener in subscriptions.items():
            service.market.unsubscribe(key,tf,listener)
