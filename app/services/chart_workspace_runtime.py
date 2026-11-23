"""One startup-owned chart workspace and run owner, never built by requests."""
from app.infra.executor import run_workspace
from app.infra.research_files import lock
from app.services.chart_workspace_store import ChartWorkspaceStore
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.services.chart_workspace_runs import ChartPineRuns


class ChartWorkspaceRuntime:
    def __init__(self, binance, indexes, *, root=None):
        self.store = ChartWorkspaceStore(root)
        self._ownership = lock(self.store.root / "runtime-owner")
        try:
            self._ownership.__enter__()
        except OSError as exc:
            raise RuntimeError("已有 API 进程持有图表工作台，请先停止旧进程") from exc
        try:
            self.store.seed()
            self.runs = ChartPineRuns(self.store, None)
            self.market = ChartWorkspaceMarket(binance, indexes)
            self.runs.market = self.market
            self.closed = False
        except BaseException:
            self._ownership.__exit__(None, None, None)
            raise

    async def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            await self.runs.close()
        finally:
            try:
                await self.market.close()
            finally:
                await run_workspace(lambda: self._ownership.__exit__(None, None, None))
