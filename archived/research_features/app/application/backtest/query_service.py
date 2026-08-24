from __future__ import annotations

from app.exceptions import NotFoundError
from app.application.backtest.ports import BacktestRunReader, StrategyReader
from app.infra.executor import run_database


class BacktestQueryService:
    """Read-side use cases. Routers own final API response validation."""

    def __init__(
        self,
        *,
        run_repository: BacktestRunReader,
        strategy_query_service: StrategyReader,
    ) -> None:
        self.strategy_query_service = strategy_query_service
        self.run_repository = run_repository

    async def list_strategies(self) -> list[dict]:
        return await run_database(self.strategy_query_service.list_strategies)

    async def list_templates(self) -> list[dict]:
        return await run_database(self.strategy_query_service.list_templates)

    async def get_editor_contract(self) -> dict:
        return await run_database(self.strategy_query_service.get_editor_contract)

    async def list_indicators(self) -> list[dict]:
        return await run_database(self.strategy_query_service.list_indicators)

    async def list_indicator_engines(self) -> list[dict]:
        return await run_database(self.strategy_query_service.list_indicator_engines)

    async def list_runs(self) -> list[dict]:
        return await run_database(self.run_repository.list_runs)

    async def get_run(self, backtest_id: int, page: int, page_size: int) -> dict:
        result = await run_database(lambda: self.run_repository.get_run(backtest_id, page, page_size))
        if result is None:
            raise NotFoundError("回测记录不存在")
        return result

    async def list_paper_runs(self) -> list[dict]:
        return await run_database(lambda: self.run_repository.list_runs("paper_live"))

    async def get_paper_run(self, run_id: int, page: int, page_size: int) -> dict:
        result = await run_database(
            lambda: self.run_repository.get_run(run_id, page, page_size, "paper_live")
        )
        if result is None:
            raise NotFoundError("模拟盘记录不存在")
        return result
