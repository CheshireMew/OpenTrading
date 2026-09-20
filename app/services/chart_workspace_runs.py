from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path

from app.contracts.chart_workspace import PineRun, PineRunRequest, WorkspaceWrite
from app.infra.worker_process import start_worker
from app.services.chart_workspace_store import ROOT
from app.services.chart_workspace_market import close_boundary
from app.services.chart_workspace_engine import freeze_engine, engine_worker


class ChartPineRuns:
    def __init__(self, store, market):
        self.store, self.market = store, market
        self.tasks = {}
        self.processes = {}
        for doc in store.list("runs"):
            if doc.data["status"] in {"queued", "loading", "running"}:
                self.update(doc.id,status="interrupted",error="应用在上次运行中退出，可使用已保存的快照重新运行")

    def folder(self, key):
        # IDs are minted here, and API lookups first require an existing record.
        self.store.get("runs",key)
        return self.store.root / "runs" / key

    def update(self,key,**values):
        doc = self.store.get("runs",key)
        doc.data.update(values)
        return self.store.put("runs",key,WorkspaceWrite(name=doc.name,data=doc.data,expected_version=doc.version))

    def list(self):
        return [PineRun.model_validate(d.data) for d in self.store.list("runs")]

    def get(self,key):
        data = self.store.get("runs",key).data
        progress = self.folder(key) / "progress.json"
        if data["status"] == "running" and progress.exists():
            data["progress"] = json.loads(progress.read_text())["progress"]
        return PineRun.model_validate(data)

    def create(self,request: PineRunRequest,api: str, *, frozen_from=None):
        script = self.store.get("scripts",request.script_id,request.script_version)
        if request.start >= request.end:
            raise ValueError("结束时间必须晚于开始时间")
        key = uuid.uuid4().hex
        run = PineRun(id=key,status="queued",created_at=int(time.time()*1000),request=request)
        self.store.put("runs",key,WorkspaceWrite(name=script.name,data=run.model_dump()))
        folder = self.folder(key)
        folder.mkdir(parents=True,exist_ok=True)
        self.tasks[key] = asyncio.create_task(self.execute(key,script,api,frozen_from))
        self.tasks[key].add_done_callback(lambda _: self.tasks.pop(key,None))
        return run

    async def execute(self,key,script,api,frozen_from):
        folder = self.folder(key)
        job = process = None
        try:
            request = self.get(key).request
            self.update(key,status="loading")
            if frozen_from:
                original = self.folder(frozen_from)
                if not (original/"input.json").exists():
                    raise ValueError("上次未完成数据快照，请新建运行")
                payload = json.loads((original/"input.json").read_text(encoding="utf-8"))
                if not payload.get("engine_snapshot"):
                    raise ValueError("此旧记录未保存引擎文件快照，请新建运行；旧结果仍可查看")
                if (original/"series.json").exists():
                    payload["series"] = json.loads((original/"series.json").read_text(encoding="utf-8"))
                payload.update(frozen=True,api=api)
            else:
                info = await self.market.resolve(request.symbol)
                if request.timeframe not in info.timeframes or info.market == "index":
                    raise ValueError("该品种暂不提供经过成交模拟验证的 OHLC 数据")
                bars, cursor = [], request.start
                while cursor <= request.end:
                    data = await self.market.bars(request.symbol,request.timeframe,limit=1000,start=cursor,end=request.end)
                    batch = [b for b in data.bars if b.closed and b.closeTime <= request.end]
                    if not batch:
                        break
                    if batch[0].time < cursor or batch[-1].closeTime <= cursor:
                        raise ValueError("行情分页没有前进，运行已停止")
                    for previous, current in zip(batch, batch[1:]):
                        if previous.closeTime != current.time:
                            raise ValueError("运行区间有行情缺口，请补齐数据后重试")
                    if any(not (b.low <= min(b.open,b.close) <= max(b.open,b.close) <= b.high) or b.volume < 0 for b in batch):
                        raise ValueError("行情 OHLCV 数据无效，未执行成交模拟")
                    if bars and batch[0].time != bars[-1].closeTime:
                        raise ValueError("运行区间有行情缺口，请补齐数据后重试")
                    bars.extend(batch)
                    cursor = batch[-1].closeTime
                    self.update(key,progress=min(99,(cursor-request.start)/(request.end-request.start)*100))
                if len(bars)<2:
                    raise ValueError("运行区间不足两根已收盘 K 线")
                if bars[0].time > close_boundary(request.start,request.timeframe):
                    raise ValueError("请求的开始时间早于可用行情，请调整区间")
                if bars[-1].closeTime < request.end and close_boundary(bars[-1].closeTime,request.timeframe) <= request.end:
                    raise ValueError("结束区间数据不完整，未生成收益结果")
                payload = {"source":script.data["source"],"request":request.model_dump(),"symbol":info.model_dump(),
                    "bars":[b.model_dump() for b in bars],"api":api,"engine_snapshot":freeze_engine(self.store.root)}
            worker = engine_worker(self.store.root,payload["engine_snapshot"])
            (folder/"input.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
            self.update(key,status="running",progress=0)
            node = shutil.which("node") or r"D:\Tools\NodeJS\node.exe"
            with (folder/"worker.log").open("wb") as log:
                process,job = start_worker([node,str(worker),str(folder)],stdout=log,stderr=log,cwd=ROOT)
                self.processes[key] = process
                while process.poll() is None:
                    await asyncio.sleep(.25)
            error = folder/"error.json"
            if process.returncode or error.exists():
                raise ValueError(json.loads(error.read_text(encoding="utf-8"))["error"] if error.exists() else f"Pine 进程异常退出 ({process.returncode})")
            result = json.loads((folder/"result.json").read_text(encoding="utf-8"))
            self.update(key,status="completed",progress=100,summary=result["summary"],provenance=result["provenance"])
        except asyncio.CancelledError:
            if process and process.poll() is None:
                process.terminate()
                await asyncio.to_thread(process.wait)
            if self.get(key).status not in {"cancelled","interrupted"}:
                self.update(key,status="interrupted",error="应用退出，运行已中断")
            raise
        except Exception as exc:
            self.update(key,status="failed",error=str(exc))
        finally:
            self.processes.pop(key,None)
            if job:
                job.close()

    async def cancel(self,key):
        run = self.get(key)
        if run.status not in {"queued","loading","running"}:
            return run
        self.update(key,status="cancelled")
        task = self.tasks.get(key)
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        return self.get(key)

    def records(self,key,kind,offset,limit):
        if kind == "bars":
            file = self.folder(key)/"input.json"
            records = json.loads(file.read_text(encoding="utf-8"))["bars"] if file.exists() else []
            return {"items":records[offset:offset+limit],"total":len(records),"offset":offset}
        file = self.folder(key)/"result.json"
        if not file.exists():
            return {"items":[],"total":0,"offset":offset}
        records = json.loads(file.read_text(encoding="utf-8")).get(kind,[])
        return {"items":records[offset:offset+limit],"total":len(records),"offset":offset}

    async def close(self):
        for key,task in list(self.tasks.items()):
            self.update(key,status="interrupted",error="应用退出，使用快照可以重新运行")
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)
