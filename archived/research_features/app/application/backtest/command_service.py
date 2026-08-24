from __future__ import annotations

from app.contracts.backtest import (
    BacktestPreviewCommand,
    BacktestStartCommand,
    CreateIndicatorDefinitionCommand,
    CreateStrategyTemplateCommand,
    CreateStrategyVersionCommand,
    EvolveStrategyFromBacktestCommand,
    PaperStartCommand,
)
from app.exceptions import BadRequestError, NotFoundError
from app.application.backtest.paper_manager import PaperRunManager
from app.application.backtest.preview_service import BacktestPreviewService
from app.application.backtest.run_service import BacktestRunService
from app.application.backtest.ports import BacktestRunReader, StrategyReader, StrategyWriter
from app.domain.backtest.scripted_templates import template_supports_paper
from app.domain.backtest.strategy_catalog import get_template_runtime_contract
from app.application.backtest.strategy_evolution_service import StrategyEvolutionService
from app.domain.backtest.strategy_support import (
    build_strategy_version_response_payload,
)
from app.infra.executor import run_compute, run_database
from utils.logger import logger


class BacktestCommandService:
    def __init__(
        self,
        *,
        run_service: BacktestRunService,
        preview_service: BacktestPreviewService,
        paper_manager: PaperRunManager,
        run_repository: BacktestRunReader,
        strategy_query_service: StrategyReader,
        strategy_write_service: StrategyWriter,
    ) -> None:
        self.strategy_query_service = strategy_query_service
        self.strategy_write_service = strategy_write_service
        self.run_service = run_service
        self.preview_service = preview_service
        self.paper_manager = paper_manager
        self.run_repository = run_repository
        self.strategy_evolution_service = StrategyEvolutionService(
            run_repository=run_repository,
            strategy_query_service=strategy_query_service,
            strategy_write_service=strategy_write_service,
        )

    async def preview_backtest(self, command: BacktestPreviewCommand) -> dict:
        strategy = self.strategy_query_service.get_strategy_version(
            command.strategy_key, command.strategy_version
        )
        logger.info(
            f"生成策略预览: strategy={command.strategy_key} v{command.strategy_version or 'default'}, "
            f"symbols={','.join(command.portfolio.symbols)}, tf={command.timeframe}, "
            f"range=({command.start_datetime} - {command.end_datetime})"
        )
        return await run_compute(
            lambda: self.preview_service.build_preview(
                strategy=strategy,
                command=command,
            ),
        )

    async def start_backtest(self, command: BacktestStartCommand) -> dict:
        strategy = self.strategy_query_service.get_strategy_version(
            command.strategy_key, command.strategy_version
        )
        approved_preview = self.preview_service.require_approved(
            preview_id=command.preview_id,
            approved_fingerprint=command.approved_fingerprint,
            strategy=strategy,
            command=command.preview_command(),
        )
        logger.info(
            f"启动回测: strategy={command.strategy_key} v{command.strategy_version or 'default'}, "
            f"symbols={','.join(command.portfolio.symbols)}, tf={command.timeframe}, "
            f"range=({command.start_datetime} - {command.end_datetime}), "
            f"本金={command.initial_cash}, 手续费={command.fee_rate}%"
        )

        backtest_id = await run_compute(
            lambda: self.run_service.run_backtest(
                strategy=strategy,
                portfolio=command.portfolio,
                research=command.research,
                start_date=command.start_datetime,
                end_date=command.end_datetime,
                timeframe=command.timeframe,
                initial_cash=command.initial_cash,
                fee_rate=command.fee_rate,
                preview_id=command.preview_id,
                preview_fingerprint=command.approved_fingerprint,
                preview_artifact=approved_preview.artifact,
            ),
        )
        if not backtest_id:
            raise RuntimeError("回测执行失败")
        return {"success": True, "backtest_id": backtest_id, "message": "回测已完成"}

    async def start_paper_run(self, command: PaperStartCommand) -> dict:
        strategy = self.strategy_query_service.get_strategy_version(
            command.strategy_key, command.strategy_version
        )
        runtime_contract = get_template_runtime_contract(strategy.template)
        if not template_supports_paper(runtime_contract):
            raise BadRequestError("该策略当前只支持回测，不支持模拟盘")
        logger.info(
            f"启动模拟盘: strategy={strategy.strategy_key} v{strategy.version}, "
            f"symbols={','.join(command.portfolio.symbols)}, tf={command.timeframe}, "
            f"本金={command.initial_cash}, 手续费={command.fee_rate}%"
        )
        return await self.paper_manager.start_run(command)

    async def stop_paper_run(self, run_id: int) -> dict:
        logger.info(f"停止模拟盘: run_id={run_id}")
        return await self.paper_manager.stop_run(run_id)

    async def delete_backtest(self, backtest_id: int) -> dict:
        logger.info(f"删除回测记录: backtest_id={backtest_id}")
        deleted = await run_database(
            lambda: self.run_repository.delete_run(backtest_id, "backtest"),
        )
        if not deleted:
            raise NotFoundError(f"回测记录不存在: {backtest_id}")
        return {"success": True, "run_id": backtest_id, "message": "回测记录已删除"}

    async def delete_paper_run(self, run_id: int) -> dict:
        logger.info(f"删除模拟盘记录: run_id={run_id}")
        return await self.paper_manager.delete_run(run_id)

    async def create_template(
        self, command: CreateStrategyTemplateCommand
    ) -> dict:
        result = await run_database(
            lambda: self.strategy_write_service.create_template(
                key=command.key,
                name=command.name,
                category=command.category,
                description=command.description,
                indicator_keys=command.indicator_keys,
                default_config=command.default_config,
                default_parameter_space=command.default_parameter_space,
            ),
        )
        return result

    async def create_indicator(
        self, command: CreateIndicatorDefinitionCommand
    ) -> dict:
        result = await run_database(
            lambda: self.strategy_write_service.create_indicator(
                key=command.key,
                name=command.name,
                engine_key=command.engine_key,
                description=command.description,
                params=command.params,
            ),
        )
        return result

    async def create_strategy_version(
        self, command: CreateStrategyVersionCommand
    ) -> dict:
        result = await run_database(
            lambda: self.strategy_write_service.create_strategy_version(
                key=command.key,
                name=command.name,
                template=command.template,
                category=command.category,
                description=command.description,
                config=command.config,
                parameter_space=command.parameter_space,
                notes=command.notes,
                make_default=command.make_default,
            ),
        )
        return build_strategy_version_response_payload(result)

    async def evolve_strategy_from_backtest(
        self, command: EvolveStrategyFromBacktestCommand
    ) -> dict:
        return await run_compute(
            lambda: self.strategy_evolution_service.evolve_from_backtest(command),
        )
