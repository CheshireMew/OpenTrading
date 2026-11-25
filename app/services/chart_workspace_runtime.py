"""One startup-owned chart workspace and run owner, never built by requests."""
from app.infra.executor import run_workspace
from app.infra.research_files import lock
from app.services.chart_workspace_seed import seed_workspace
from app.infra.persistence.chart_workspace_repository import ChartWorkspaceStore
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.services.chart_daily_history import ChartDailyHistory
from app.services.chart_workspace_runs import ChartPineRuns


class ChartWorkspaceRuntime:
    def __init__(self, binance, indexes, *, root=None, kline_store=None, market_data=None):
        self.store = ChartWorkspaceStore(root)
        self._ownership = lock(self.store.root / "runtime-owner")
        try:
            self._ownership.__enter__()
        except OSError as exc:
            raise RuntimeError("已有 API 进程持有图表工作台，请先停止旧进程") from exc
        try:
            seed_workspace(self.store)
            self.runs = ChartPineRuns(self.store, None)
            self.market = ChartWorkspaceMarket(binance, indexes, kline_store=kline_store,
                daily_history=ChartDailyHistory(market_data) if market_data is not None else None)
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
