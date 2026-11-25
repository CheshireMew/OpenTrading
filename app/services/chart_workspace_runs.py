from __future__ import annotations

import asyncio
import json
import subprocess
import time
import uuid

from app.contracts.chart_workspace import PineProgress, PineRun, PineRunRequest, WorkspaceWrite, WorkspaceDocument
from app.infra.worker_process import start_worker
from app.infra.node_runtime import resolve_node
from app.infra.executor import run_workspace
from config.settings import BASE_DIR as ROOT
from app.services.chart_workspace_market import close_boundary
from app.services.chart_workspace_engine import freeze_engine, engine_worker
from config import settings
from app.infra.persistence.pine_record_repository import PineRecordStore


class PineCapacityError(ValueError):
    pass


class ChartPineRuns:
    def __init__(self, store, market, *, concurrency=None, queue_limit=None, timeout=None, queue_timeout=None):
        self.store, self.market = store, market
        self.store.migrate_run_progress()
        self.tasks = {}
        self.processes = {}
        self.closed = False
        self.concurrency = concurrency if concurrency is not None else settings.PINE_RUN_CONCURRENCY
        self.queue_limit = queue_limit if queue_limit is not None else settings.PINE_RUN_QUEUE_LIMIT
        self.timeout = timeout if timeout is not None else settings.PINE_RUN_TIMEOUT_SECONDS
        self.queue_timeout = queue_timeout if queue_timeout is not None else settings.PINE_RUN_QUEUE_TIMEOUT_SECONDS
        if self.concurrency < 1 or self.queue_limit < 0 or self.timeout <= 0 or self.queue_timeout <= 0:
            raise ValueError("Pine 运行容量及超时配置无效")
        self.slots = asyncio.Semaphore(self.concurrency)
        self.submissions = asyncio.Lock()
        for doc in store.list("runs"):
            if doc.data["status"] in {"queued", "loading", "running"}:
                self.update(doc.id,status="interrupted",error="应用在上次运行中退出，可使用已保存的快照重新运行")

    def folder(self, key):
        # IDs are minted here, and API lookups first require an existing record.
        self.store.get("runs",key)
        return self.store.root / "runs" / key

    def update(self,key,**values):
        return self.store.patch_run(key, values)

    async def _update(self, key, **values):
        return await run_workspace(lambda: self.update(key, **values))

    def list(self):
        return [PineRun.model_validate(d.data) for d in self.store.list("runs")]

    def get(self,key):
        data = self.store.get("runs",key).data
        progress = self.folder(key) / "progress.json"
        if data["status"] == "running" and progress.exists():
            try:
                frame = json.loads(progress.read_text())
                # Frozen historical engines may lack this progress protocol. Their
                # results remain usable; unowned telemetry is never a measurement.
                if frame.get("runId") == key:
                    data["progress"] = PineProgress.model_validate(frame["progress"]).model_dump()
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                # Telemetry cannot invalidate the durable lifecycle/result.
                data["progress"] = {"phase":"computing","mode":"indeterminate"}
        return PineRun.model_validate(data)

    async def create(self,request: PineRunRequest,api: str, *, frozen_from=None, recording="research"):
        async with self.submissions:
            if self.closed:
                raise PineCapacityError("Pine 运行服务已关闭")
            if sum(not task.done() for task in self.tasks.values()) >= self.concurrency + self.queue_limit:
                raise PineCapacityError("Pine 运行队列已满，请等待现有任务结束后重试")
            if request.start >= request.end:
                raise ValueError("结束时间必须晚于开始时间")
            if recording not in {"report", "research"}:
                raise ValueError("未知回测保存方式")
            if frozen_from and self.get(frozen_from).recording == "report":
                raise ValueError("本次仅保存回测报告，请按所需参数重新运行")
            # Browser-owned scripts are supplied for this explicit computation;
            # never create or update a server-side personal script document.
            script = WorkspaceDocument(id=request.script_id, name=request.script_name or request.script_id,
                version=request.script_version, data={"source": request.script_source, "language": "pine"},
                updated_at=int(time.time()*1000)) if request.script_source is not None else await run_workspace(
                    lambda: self.store.get("scripts",request.script_id,request.script_version))
            key = uuid.uuid4().hex
            run = PineRun(id=key,status="queued",created_at=int(time.time()*1000),request=request,recording=recording)
            def persist():
                self.store.put("runs",key,WorkspaceWrite(name=script.name,data=run.model_dump()))
                (self.store.root / "runs" / key).mkdir(parents=True,exist_ok=True)
            writing = asyncio.create_task(run_workspace(persist))
            try:
                await asyncio.shield(writing)
            except asyncio.CancelledError:
                await writing
                await self._update(key,status="interrupted",error="提交请求已中断，可使用已保存记录重新运行")
                raise
            self.tasks[key] = asyncio.create_task(self.execute(key,script,api,frozen_from))
            self.tasks[key].add_done_callback(lambda _: self.tasks.pop(key,None))
            return run

    async def execute(self,key,script,api,frozen_from):
        acquired = False
        try:
            try:
                async with asyncio.timeout(self.queue_timeout):
                    await self.slots.acquire()
                acquired = True
            except TimeoutError:
                await self._update(key,status="failed",error="等待运行资源超时，请稍后重新运行")
                return
            async with asyncio.timeout(self.timeout):
                await self._execute(key,script,api,frozen_from)
        except TimeoutError:
            await self._update(key,status="failed",error=f"运行超过 {self.timeout:g} 秒，已终止对应进程")
        except asyncio.CancelledError:
            await self._update(key,status="interrupted",error="应用退出，运行已中断")
            raise
        finally:
            if acquired:
                self.slots.release()

    async def _execute(self,key,script,api,frozen_from):
        folder = self.store.root / "runs" / key
        job = process = None
        report_task = None
        try:
            run = await run_workspace(lambda: self.get(key))
            request, report_only = run.request, run.recording == "report"
            await self._update(key,status="loading",progress={"phase":"loading","mode":"indeterminate"})
            if frozen_from:
                original = await run_workspace(lambda: self.folder(frozen_from))
                if not (original/"input.json").exists():
                    raise ValueError("上次未完成数据快照，请新建运行")
                payload = await asyncio.to_thread(lambda: json.loads((original/"input.json").read_text(encoding="utf-8")))
                if not payload.get("engine_snapshot"):
                    raise ValueError("此旧记录未保存引擎文件快照，请新建运行；旧结果仍可查看")
                if (original/"series.json").exists():
                    payload["series"] = await asyncio.to_thread(lambda: json.loads((original/"series.json").read_text(encoding="utf-8")))
                payload.update(frozen=True,api=api)
            else:
                info = await self.market.resolve(request.symbol)
                if request.timeframe not in info.timeframes or info.market not in {"spot", "usdm"}:
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
                    await self._update(key,progress={"phase":"loading","mode":"indeterminate","completed":len(bars),"unit":"candles"})
                if len(bars)<2:
                    raise ValueError("运行区间不足两根已收盘 K 线")
                if bars[0].time > close_boundary(request.start,request.timeframe):
                    raise ValueError("请求的开始时间早于可用行情，请调整区间")
                if bars[-1].closeTime < request.end and close_boundary(bars[-1].closeTime,request.timeframe) <= request.end:
                    raise ValueError("结束区间数据不完整，未生成收益结果")
                payload = {"source":script.data["source"],"request":request.model_dump(),"symbol":info.model_dump(),
                    "bars":[b.model_dump() for b in bars],"api":api}
                if not report_only:
                    payload["engine_snapshot"] = await asyncio.to_thread(freeze_engine,self.store.root)
            payload["runId"] = key
            if report_only:
                worker = ROOT / "frontend/scripts/pine-workspace-worker.mjs"
            else:
                worker = await asyncio.to_thread(engine_worker,self.store.root,payload["engine_snapshot"])
                await asyncio.to_thread(lambda: (folder/"input.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8"))
            await self._update(key,status="running",progress={"phase":"computing","mode":"indeterminate"})
            node = resolve_node()
            def spawn():
                with (folder/"worker.log").open("wb") as log:
                    command = [node,str(worker),str(folder)]
                    if report_only:
                        return start_worker([*command,"--report"],input_payload=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
                                            stdout=subprocess.PIPE,stderr=log,cwd=ROOT)
                    return start_worker(command,stdout=log,stderr=log,cwd=ROOT)
            spawning = asyncio.create_task(run_workspace(spawn))
            try:
                process, job = await asyncio.shield(spawning)
            except asyncio.CancelledError:
                # Cancelling an executor Future cannot stop OS process creation.
                # Reclaim the actual returned handles before cancellation exits.
                process, job = await spawning
                raise
            self.processes[key] = process
            if report_only:
                report_task = asyncio.create_task(asyncio.to_thread(PineRecordStore(folder).consume_report, process.stdout))
            while process.poll() is None:
                if report_task is not None and report_task.done():
                    report_task.result()
                await asyncio.sleep(.25)
            error = folder/"error.json"
            if process.returncode or error.exists():
                raise ValueError(json.loads(error.read_text(encoding="utf-8"))["error"] if error.exists() else f"Pine 进程异常退出 ({process.returncode})")
            def finalize():
                result = json.loads((folder/"result.json").read_text(encoding="utf-8"))
                PineRecordStore(folder).page("equity", 0, 1)
                return result["summary"], result["provenance"]
            summary, provenance = await asyncio.shield(report_task) if report_only else await asyncio.to_thread(finalize)
            await self._update(key,status="completed",progress=None,summary=summary,provenance=provenance)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._update(key,status="failed",error=str(exc))
        finally:
            if process and process.poll() is None:
                process.terminate()
            self.processes.pop(key,None)
            if job:
                job.close()
            if process:
                try:
                    await asyncio.to_thread(process.wait, timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait)
            if report_task is not None:
                await asyncio.gather(report_task, return_exceptions=True)
            if process and process.stdout:
                process.stdout.close()

    async def cancel(self,key):
        run = await run_workspace(lambda: self.get(key))
        if run.status not in {"queued","loading","running"}:
            return run
        await self._update(key,status="cancelled")
        task = self.tasks.get(key)
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        return await run_workspace(lambda: self.get(key))

    def records(self,key,kind,offset,limit, *, sampled=False):
        store = PineRecordStore(self.folder(key))
        return store.sampled_equity(limit) if kind == "equity" and sampled else store.page(kind,offset,limit)

    async def close(self):
        async with self.submissions:
            self.closed = True
        tasks = list(self.tasks.items())
        for key, task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*(task for _, task in tasks),return_exceptions=True)
        for key, _ in tasks:
            await self._update(key,status="interrupted",error="应用退出，使用快照可以重新运行")
