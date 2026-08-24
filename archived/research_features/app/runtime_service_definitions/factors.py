from __future__ import annotations

from app.runtime import runtime_role_has_target
from app.runtime_definition import RuntimeBuildContext, RuntimeServiceDefinition
from app.runtime_lifecycle import start_paper_run_monitoring, shutdown_service
from app.runtime_refs import (
    BACKTEST_FACTOR_PAPER_RUN_WRITER,
    BACKTEST_FACTOR_RUN_WRITER,
    BACKTEST_PAPER_RUN_WRITER,
    BACKTEST_REPORT_BUILDER,
    BACKTEST_RUN_REPOSITORY,
    FACTORS_EXECUTION_SERVICE,
    FACTORS_PAPER_PERSISTENCE_SERVICE,
    FACTORS_PAPER_RUN_MANAGER,
    FACTORS_RESEARCH_REPOSITORY,
    FACTORS_RESEARCH_SERVICE,
    FACTORS_SIGNAL_EXECUTION_CORE,
    INFRA_DATABASE_RUNTIME,
    MARKET_INDICATOR_REPOSITORY,
    MARKET_MARKET_DATA_SERVICE,
)


def _build_factor_research_repository(ctx: RuntimeBuildContext):
    from app.infra.persistence.factors.repository import FactorResearchRepository

    return FactorResearchRepository(database_runtime=ctx.require(INFRA_DATABASE_RUNTIME))


def _build_factor_research_service(ctx: RuntimeBuildContext):
    from app.services.factors.service import FactorResearchService

    return FactorResearchService(
        market_data_service=ctx.require(MARKET_MARKET_DATA_SERVICE),
        indicator_repository=ctx.require(MARKET_INDICATOR_REPOSITORY),
        repository=ctx.require(FACTORS_RESEARCH_REPOSITORY),
    )


def _build_factor_execution_service(ctx: RuntimeBuildContext):
    from app.application.factors.execution import FactorExecutionService

    return FactorExecutionService(
        factor_service=ctx.require(FACTORS_RESEARCH_SERVICE),
        report_builder=ctx.require(BACKTEST_REPORT_BUILDER),
        execution_core=ctx.require(FACTORS_SIGNAL_EXECUTION_CORE),
        factor_backtest_runs=ctx.require(BACKTEST_FACTOR_RUN_WRITER),
    )


def _build_factor_signal_execution_core(_ctx: RuntimeBuildContext):
    from app.domain.factors.signal_execution_core import FactorSignalExecutionCore

    return FactorSignalExecutionCore()


def _build_factor_paper_persistence_service(ctx: RuntimeBuildContext):
    from app.application.factors.paper_persistence_service import FactorPaperPersistenceService

    return FactorPaperPersistenceService(
        paper_runs=ctx.require(BACKTEST_PAPER_RUN_WRITER),
        factor_paper_runs=ctx.require(BACKTEST_FACTOR_PAPER_RUN_WRITER),
        report_builder=ctx.require(BACKTEST_REPORT_BUILDER),
        execution_core=ctx.require(FACTORS_SIGNAL_EXECUTION_CORE),
    )


def _build_factor_paper_run_manager(ctx: RuntimeBuildContext):
    from app.application.factors.paper_manager import FactorPaperRunManager

    return FactorPaperRunManager(
        factor_service=ctx.require(FACTORS_RESEARCH_SERVICE),
        run_repository=ctx.require(BACKTEST_RUN_REPOSITORY),
        report_builder=ctx.require(BACKTEST_REPORT_BUILDER),
        execution_core=ctx.require(FACTORS_SIGNAL_EXECUTION_CORE),
        persistence_service=ctx.require(FACTORS_PAPER_PERSISTENCE_SERVICE),
        paper_runs=ctx.require(BACKTEST_PAPER_RUN_WRITER),
        activate_created_runs=runtime_role_has_target(ctx.role, "background"),
    )


FACTOR_SERVICE_DEFINITIONS: tuple[RuntimeServiceDefinition, ...] = (
    RuntimeServiceDefinition(
        FACTORS_RESEARCH_REPOSITORY,
        frozenset({"api", "background"}),
        _build_factor_research_repository,
        deps=(INFRA_DATABASE_RUNTIME,),
    ),
    RuntimeServiceDefinition(
        FACTORS_RESEARCH_SERVICE,
        frozenset({"api", "background"}),
        _build_factor_research_service,
        deps=(MARKET_MARKET_DATA_SERVICE, MARKET_INDICATOR_REPOSITORY, FACTORS_RESEARCH_REPOSITORY),
    ),
    RuntimeServiceDefinition(
        FACTORS_EXECUTION_SERVICE,
        frozenset({"api"}),
        _build_factor_execution_service,
        deps=(FACTORS_RESEARCH_SERVICE, BACKTEST_REPORT_BUILDER, FACTORS_SIGNAL_EXECUTION_CORE, BACKTEST_FACTOR_RUN_WRITER),
    ),
    RuntimeServiceDefinition(
        FACTORS_SIGNAL_EXECUTION_CORE,
        frozenset({"api", "background"}),
        _build_factor_signal_execution_core,
    ),
    RuntimeServiceDefinition(
        FACTORS_PAPER_PERSISTENCE_SERVICE,
        frozenset({"api", "background"}),
        _build_factor_paper_persistence_service,
        deps=(BACKTEST_PAPER_RUN_WRITER, BACKTEST_FACTOR_PAPER_RUN_WRITER, BACKTEST_REPORT_BUILDER, FACTORS_SIGNAL_EXECUTION_CORE),
    ),
    RuntimeServiceDefinition(
        FACTORS_PAPER_RUN_MANAGER,
        frozenset({"api", "background"}),
        _build_factor_paper_run_manager,
        deps=(
            FACTORS_RESEARCH_SERVICE,
            BACKTEST_RUN_REPOSITORY,
            BACKTEST_PAPER_RUN_WRITER,
            BACKTEST_REPORT_BUILDER,
            FACTORS_SIGNAL_EXECUTION_CORE,
            FACTORS_PAPER_PERSISTENCE_SERVICE,
        ),
        background_start=start_paper_run_monitoring,
        background_stop=shutdown_service,
        background_start_order=40,
        background_stop_order=20,
    ),
)
