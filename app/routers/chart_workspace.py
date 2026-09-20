from __future__ import annotations

import asyncio
from typing import Literal
from fastapi import Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from starlette.requests import HTTPConnection
from app.contracts.frontend import FrontendContractRouter
from app.contracts.chart_workspace import (ChartSymbol, ChartBars, ChartQuote, WorkspaceDocument, WorkspaceWrite,
    PineRun, PineRunRequest, PineRecords, PineCapabilities)
from app.dependencies import get_binance_market_intel_service, get_index_data_service
from app.services.chart_workspace_store import ChartWorkspaceStore, WorkspaceConflict
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.services.chart_workspace_runs import ChartPineRuns

router = FrontendContractRouter(frontend_contract_target="chartWorkspace",prefix="/chart-workspace",tags=["图表工作台"])
Kind = Literal["layouts","watchlists","scripts"]


class WorkspaceServices:
    def __init__(self, connection):
        self.store = ChartWorkspaceStore()
        self.store.seed()
        self.market = ChartWorkspaceMarket(get_binance_market_intel_service(connection),get_index_data_service(connection))
        self.runs = ChartPineRuns(self.store,self.market)

    async def close(self):
        await self.runs.close()
        await self.market.close()


def services(connection: HTTPConnection):
    if not hasattr(connection.app.state,"chart_workspace"):
        connection.app.state.chart_workspace = WorkspaceServices(connection)
    return connection.app.state.chart_workspace


def document_call(fn):
    try:
        return fn()
    except KeyError:
        raise HTTPException(404,"记录不存在")
    except WorkspaceConflict as exc:
        raise HTTPException(409,str(exc))
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@router.get("/symbols",response_model=list[ChartSymbol])
async def chart_symbols(service=Depends(services)):
    return await service.market.symbols()


@router.get("/bars",response_model=ChartBars)
async def chart_bars(symbol:str,timeframe:str,limit:int=Query(1000,ge=1,le=1000),start:int|None=None,end:int|None=None,service=Depends(services)):
    try:
        return await service.market.bars(symbol,timeframe,limit,start,end)
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@router.get("/quotes",response_model=list[ChartQuote])
async def chart_quotes(symbols:str,service=Depends(services)):
    return await service.market.quotes(list(dict.fromkeys(symbols.split(',')))[:100])


@router.get("/capabilities",response_model=PineCapabilities)
async def chart_capabilities():
    return PineCapabilities(supported=["Pine v5/v6 常用指标与 strategy", "多图、绘图、原版 v7.2", "已接入品种的多周期请求"],
        limited=["varip 支持全局标量（Heimdall 兼容层），不支持局部变量和集合", "实时计算使用实际收到的行情更新", "历史 OHLC 成交模拟不是逐 tick 还原", "USD/USDT 采用报价数值记账，不执行汇率换算"],
        unsupported=["OCA 联动", "强平价格与跨币种换算", "财报与经济数据", "外部 Pine 库", "lookahead_on", "Bar Magnifier"])


@router.get("/pine-runs",response_model=list[PineRun])
async def chart_pine_runs(service=Depends(services)):
    return service.runs.list()


@router.post("/pine-runs",response_model=PineRun)
async def chart_create_pine_run(body:PineRunRequest,request:Request,service=Depends(services)):
    return document_call(lambda:service.runs.create(body,str(request.base_url).rstrip('/')+'/api/v1/chart-workspace'))


@router.get("/pine-runs/{key}",response_model=PineRun)
async def chart_get_pine_run(key:str,service=Depends(services)):
    return document_call(lambda:service.runs.get(key))


@router.post("/pine-runs/{key}/cancel",response_model=PineRun)
async def chart_cancel_pine_run(key:str,service=Depends(services)):
    document_call(lambda:service.runs.get(key))
    return await service.runs.cancel(key)


@router.post("/pine-runs/{key}/rerun",response_model=PineRun)
async def chart_rerun_pine(key:str,request:Request,service=Depends(services)):
    previous = document_call(lambda:service.runs.get(key))
    return document_call(lambda:service.runs.create(previous.request,str(request.base_url).rstrip('/')+'/api/v1/chart-workspace',frozen_from=key))


@router.get("/pine-runs/{key}/records",response_model=PineRecords)
async def chart_pine_records(key:str,kind:Literal["equity","trades","open_trades","orders","fills","warnings","bars"]="trades",
        offset:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=10000),service=Depends(services)):
    return document_call(lambda:service.runs.records(key,kind,offset,limit))


@router.get("/{kind}",response_model=list[WorkspaceDocument])
async def chart_documents(kind:Kind,service=Depends(services)):
    return service.store.list(kind)


@router.get("/{kind}/{key}",response_model=WorkspaceDocument)
async def chart_document(kind:Kind,key:str,version:int|None=None,service=Depends(services)):
    return document_call(lambda:service.store.get(kind,key,version))


@router.put("/{kind}/{key}",response_model=WorkspaceDocument)
async def chart_save_document(kind:Kind,key:str,body:WorkspaceWrite,service=Depends(services)):
    return document_call(lambda:service.store.put(kind,key,body))


@router.post("/{kind}/{key}/archive",response_model=dict[str,bool])
async def chart_archive_document(kind:Kind,key:str,service=Depends(services)):
    document_call(lambda:service.store.archive(kind,key))
    return {"archived":True}


@router.websocket("/stream")
async def chart_stream(websocket:WebSocket):
    service = services(websocket)
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
                if len(subscriptions)>=32:
                    continue
                try:
                    info = await service.market.resolve(key)
                    if tf not in info.timeframes:
                        raise ValueError("该品种不支持此周期")
                    previous = subscriptions.get((key,tf))
                    if previous: service.market.unsubscribe(key,tf,previous)
                    listener = Subscriber(message.get("generation",0))
                    subscriptions[(key,tf)] = listener
                    service.market.subscribe(key,tf,listener)
                except ValueError as exc:
                    await websocket.send_json({"type":"status","symbol":key,"timeframe":tf,"status":"error","error":str(exc),"generation":message.get("generation",0)})
            elif message.get("type") == "unsubscribe":
                listener = subscriptions.pop((key,tf),None)
                if listener: service.market.unsubscribe(key,tf,listener)
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        for (key,tf),listener in subscriptions.items():
            service.market.unsubscribe(key,tf,listener)
