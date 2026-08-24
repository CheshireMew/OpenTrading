from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

from app.runtime_builder import validate_runtime_services
from app.runtime import AppRuntimeServices
from app.runtime_refs import (
    BACKTEST_FACTOR_PAPER_RUN_WRITER,
    BACKTEST_FACTOR_RUN_WRITER,
    BACKTEST_FREQTRADE_SERVICE,
    BACKTEST_PREVIEW_ARTIFACT_STORE,
    BACKTEST_PAPER_RUN_WRITER,
    BACKTEST_PAPER_RUN_MANAGER,
    BACKTEST_PREVIEW_SERVICE,
    BACKTEST_QUERY_SERVICE,
    BACKTEST_REPORT_BUILDER,
    BACKTEST_RUN_REPOSITORY,
    BACKTEST_RUN_SERVICE,
    BACKTEST_RUN_WRITER,
    BACKTEST_STRATEGY_DEFINITION_STORE,
    BACKTEST_STRATEGY_QUERY_SERVICE,
    BACKTEST_STRATEGY_WRITE_SERVICE,
    BACKTEST_COMMAND_SERVICE,
    FACTORS_EXECUTION_SERVICE,
    FACTORS_PAPER_PERSISTENCE_SERVICE,
    FACTORS_PAPER_RUN_MANAGER,
    FACTORS_RESEARCH_REPOSITORY,
    FACTORS_RESEARCH_SERVICE,
    FACTORS_SIGNAL_EXECUTION_CORE,
    INFRA_CACHE_SERVICE,
    INFRA_DATABASE_RUNTIME,
    INFRA_EXCHANGE_GATEWAY,
    INFRA_KLINE_STORE,
    MARKET_BINANCE_MARKET_INTEL,
    MARKET_BINANCE_MARKET_RESEARCH_STORE,
    MARKET_BINANCE_MARKET_SNAPSHOT,
    MARKET_BINANCE_WEB3_HEAT_RANKS,
    MARKET_BINANCE_WEB3_RANKS,
    MARKET_BINANCE_WEB3_TOKENS,
    MARKET_DLI_CACHE,
    MARKET_FUNDING_RATE_APP_SERVICE,
    MARKET_FUNDING_RATE_SERVICE,
    MARKET_FUNDING_RATE_STORE,
    MARKET_INDEX_DATA_SERVICE,
    MARKET_INDICATOR_REPOSITORY,
    MARKET_INDICATOR_SERVICE,
    MARKET_INSIGHT_APP_SERVICE,
    MARKET_MARKET_DATA_SERVICE,
    MARKET_QUERY_APP_SERVICE,
    MARKET_REALTIME_SERVICE,
    MARKET_WEBSOCKET_SERVICE,
    SYSTEM_CURRENCY_RATE_SERVICE,
    SYSTEM_FRED_API_CONFIG_SERVICE,
    SYSTEM_LLM_CONFIG_SERVICE,
    SYSTEM_MARKET_SCHEDULER_RUNTIME,
    TOOLS_DCA_SERVICE,
    TOOLS_PAIR_COMPARE_SERVICE,
    TOOLS_SENTIMENT_API_CLIENT,
    TOOLS_SENTIMENT_REPOSITORY,
    TOOLS_SENTIMENT_SERVICE,
    TOOLS_TOOLS_APP_SERVICE,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def _import_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_backend_contracts_have_single_source():
    assert not (APP_DIR / "schemas").exists()
    assert not (APP_DIR / "contracts" / "api").exists()
    scanned_roots = (APP_DIR, ROOT_DIR / "test", ROOT_DIR / "scripts")
    offenders = [
        path.relative_to(ROOT_DIR).as_posix()
        for root in scanned_roots
        for path in _python_files(root)
        for module in _import_modules(path)
        if module == "app.schemas"
        or module.startswith("app.schemas.")
        or module == "app.contracts.api"
        or module.startswith("app.contracts.api.")
    ]
    assert offenders == []


def test_services_do_not_depend_on_orm_schema_or_legacy_persistence_paths():
    legacy_prefixes = (
        "app.services.backtest.run_repository",
        "app.services.backtest.result_store",
        "app.services.backtest.serializers",
        "app.services.backtest.run_lifecycle",
        "app.services.backtest.strategy_catalog",
        "app.services.backtest.strategy_query_service",
        "app.services.backtest.strategy_write_service",
        "app.services.backtest.paper_manager",
        "app.services.backtest.run_service",
        "app.services.factors.repository",
        "app.services.factors.paper_persistence_service",
        "app.services.factors.paper_manager",
        "app.services.factors.execution",
        "app.services.market.kline_store",
        "app.services.market.funding_rate_store",
        "app.services.market.indicator_repository",
        "app.services.market.binance_market_research_store",
        "app.services.sentiment_repository",
        "app.services.data_retention",
        "app.services.paper_run_lifecycle",
        "app.services.market_cron",
    )
    forbidden_prefixes = ("app.infra.db", "app.infra.persistence", *legacy_prefixes)
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for path in _python_files(APP_DIR / "services")
        for module in _import_modules(path)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]
    assert offenders == []


def test_infra_persistence_does_not_depend_on_services():
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for path in _python_files(APP_DIR / "infra" / "persistence")
        for module in _import_modules(path)
        if module == "app.services" or module.startswith("app.services.")
    ]
    assert offenders == []


def test_infra_persistence_does_not_assemble_api_dtos():
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for path in _python_files(APP_DIR / "infra" / "persistence")
        for module in _import_modules(path)
        if module == "app.contracts.dto" or module.startswith("app.contracts.dto.")
    ]
    assert offenders == []


def test_backtest_use_cases_live_in_application_boundary_only():
    legacy_files = [
        APP_DIR / "services" / "backtest" / "command_service.py",
        APP_DIR / "services" / "backtest" / "query_service.py",
        APP_DIR / "services" / "backtest" / "strategy_evolution_service.py",
    ]
    assert [path.relative_to(ROOT_DIR).as_posix() for path in legacy_files if path.exists()] == []

    legacy_modules = (
        "app.services.backtest.command_service",
        "app.services.backtest.query_service",
        "app.services.backtest.strategy_evolution_service",
    )
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for root in (APP_DIR, ROOT_DIR / "test", ROOT_DIR / "scripts")
        for path in _python_files(root)
        for module in _import_modules(path)
        if any(module == legacy or module.startswith(f"{legacy}.") for legacy in legacy_modules)
    ]
    assert offenders == []


def test_backtest_run_write_repositories_have_narrow_boundaries():
    removed_path = APP_DIR / "infra" / "persistence" / "backtest" / ("run_" + "mutation_service.py")
    assert not removed_path.exists()
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in [
            APP_DIR / "infra" / "persistence" / "backtest" / "backtest_run_writer.py",
            APP_DIR / "infra" / "persistence" / "backtest" / "paper_run_writer.py",
            APP_DIR / "infra" / "persistence" / "backtest" / "factor_backtest_run_writer.py",
            APP_DIR / "infra" / "persistence" / "backtest" / "factor_paper_run_writer.py",
        ]
    }

    for removed_helper in [
        "replace_paper_snapshot",
        "persist_factor_paper_increment",
        "mark_paper_stopped",
        "update_paper_metadata",
        "report_builder",
        "execution_core",
    ]:
        assert all(removed_helper not in source for source in sources.values())

    assert "store_completed_result" in sources["backtest_run_writer.py"]
    assert "store_paper_snapshot" not in sources["backtest_run_writer.py"]
    assert "store_paper_snapshot" in sources["paper_run_writer.py"]
    assert "append_factor_paper_increment" not in sources["paper_run_writer.py"]
    assert "append_factor_paper_increment" in sources["factor_paper_run_writer.py"]


def test_domain_does_not_depend_on_infra_application_or_services():
    forbidden_prefixes = ("app.infra", "app.application", "app.services", "app.contracts.dto")
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for path in _python_files(APP_DIR / "domain")
        for module in _import_modules(path)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]
    assert offenders == []


def test_backtest_domain_contracts_have_no_dto_shadow_source():
    moved_contracts = {
        "strategy_contract.py": "strategy.py",
        "backtest_result.py": "backtest_result.py",
        "json_types.py": "json_types.py",
    }
    for old_name, new_name in moved_contracts.items():
        assert not (APP_DIR / "contracts" / "dto" / old_name).exists()
        assert (APP_DIR / "contracts" / new_name).exists()

    legacy_modules = (
        "app.contracts.dto.strategy_contract",
        "app.contracts.dto.backtest_result",
        "app.contracts.dto.json_types",
    )
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for root in (APP_DIR, ROOT_DIR / "test", ROOT_DIR / "scripts")
        for path in _python_files(root)
        for module in _import_modules(path)
        if any(module == legacy or module.startswith(f"{legacy}.") for legacy in legacy_modules)
    ]
    assert offenders == []


def test_backtest_domain_and_services_do_not_depend_on_api_dtos():
    scanned_roots = (APP_DIR / "domain" / "backtest", APP_DIR / "services" / "backtest")
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for root in scanned_roots
        for path in _python_files(root)
        for module in _import_modules(path)
        if module == "app.contracts.dto" or module.startswith("app.contracts.dto.")
    ]
    assert offenders == []


def test_services_do_not_assemble_api_dtos():
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for path in _python_files(APP_DIR / "services")
        for module in _import_modules(path)
        if (module == "app.contracts.dto" or module.startswith("app.contracts.dto."))
    ]
    assert offenders == []


def test_market_payload_builders_have_no_api_dto_shadow_source():
    dto_source = (APP_DIR / "contracts" / "dto" / "market.py").read_text(encoding="utf-8")
    contract_source = (APP_DIR / "contracts" / "market_history.py").read_text(encoding="utf-8")

    for old_helper in [
        "build_market_history_response",
        "build_market_history_batch_response",
        "build_kline_tail_response",
        "build_current_price_response",
        "build_realtime_response",
        "build_ohlcv_points",
    ]:
        assert f"def {old_helper}" not in dto_source
    for helper in [
        "build_market_history_payload",
        "build_market_history_batch_payload",
        "build_kline_tail_payload",
        "build_current_price_payload",
        "build_realtime_payload",
        "build_ohlcv_point_payloads",
    ]:
        assert f"def {helper}" in contract_source


def test_backtest_workspaces_are_never_deleted_for_parameter_reuse():
    source = (APP_DIR / "services" / "backtest" / "freqtrade_execution.py").read_text(encoding="utf-8")

    assert "shutil.rmtree" not in source
    assert "uuid4().hex" in source
    assert "拒绝覆盖" in source


def test_paper_run_lifecycle_uses_active_monitoring_not_restore_only():
    scanned = [
        APP_DIR / "application" / "run_task_manager.py",
        APP_DIR / "application" / "paper_run_lifecycle.py",
        APP_DIR / "runtime_lifecycle.py",
        APP_DIR / "runtime_service_definitions" / "backtest.py",
        APP_DIR / "runtime_service_definitions" / "factors.py",
    ]
    sources = "\n".join(path.read_text(encoding="utf-8") for path in scanned)

    assert "restore_active_runs" not in sources
    assert "restore_paper_runs" not in sources
    assert "start_active_run_monitoring" in sources
    assert "_discover_active_runs_loop" in sources


def test_blocking_work_uses_bounded_executor_boundary():
    source = (APP_DIR / "infra" / "executor.py").read_text(encoding="utf-8")
    frontend_request = (ROOT_DIR / "frontend" / "src" / "api" / "request.ts").read_text(encoding="utf-8")

    assert "ThreadPoolExecutor" in source
    for boundary in [
        "run_database",
        "run_compute",
        "run_external_io",
        "run_background",
    ]:
        assert f"async def {boundary}" in source
    assert "run_sync" not in source
    assert "_blocking_executor" not in source
    assert "BLOCKING_DATABASE_MAX_WORKERS" in source
    assert "BLOCKING_COMPUTE_MAX_WORKERS" in source
    assert "BLOCKING_EXTERNAL_IO_MAX_WORKERS" in source
    assert "BLOCKING_BACKGROUND_MAX_WORKERS" in source
    assert "run_in_executor(None" not in source
    assert "longTask: createClient(0)" not in frontend_request


def test_backtest_run_metadata_has_no_wide_response_model():
    removed_symbol = "BacktestRunMetadataResponse"
    offenders = [
        path.relative_to(ROOT_DIR).as_posix()
        for root in (APP_DIR, ROOT_DIR / "test", ROOT_DIR / "scripts")
        for path in _python_files(root)
        if path != Path(__file__).resolve()
        and removed_symbol in path.read_text(encoding="utf-8-sig")
    ]
    assert offenders == []


def test_application_does_not_open_orm_boundary_directly():
    offenders = [
        path.relative_to(ROOT_DIR).as_posix()
        for path in _python_files(APP_DIR / "application")
        if "session_scope(" in path.read_text(encoding="utf-8-sig")
        or any(
            module == "app.infra.db.schema" or module.startswith("app.infra.db.schema.")
            for module in _import_modules(path)
        )
    ]
    assert offenders == []


def test_application_boundary_uses_ports_instead_of_concrete_infra_services_or_api_dtos():
    forbidden_prefixes = ("app.infra.db", "app.infra.persistence", "app.services", "app.contracts.dto")
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for path in _python_files(APP_DIR / "application")
        for module in _import_modules(path)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]
    assert offenders == []


def test_routers_do_not_import_concrete_services_or_infra():
    forbidden_prefixes = ("app.services", "app.infra")
    offenders = [
        f"{path.relative_to(ROOT_DIR).as_posix()} -> {module}"
        for path in _python_files(APP_DIR / "routers")
        for module in _import_modules(path)
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]
    assert offenders == []


def test_backtest_run_lifecycle_status_has_contract_source_only():
    lifecycle_source = (APP_DIR / "infra" / "persistence" / "backtest" / "run_lifecycle.py").read_text(encoding="utf-8")
    contract_source = (APP_DIR / "contracts" / "backtest_run.py").read_text(encoding="utf-8")

    for symbol in ["RUN_STATUS_RUNNING", "RUN_STATUS_COMPLETED", "RUN_STATUS_FAILED", "RUN_STATUS_STOPPED"]:
        assert f"{symbol} =" not in lifecycle_source
        assert f"{symbol} =" in contract_source


def test_runtime_role_controls_registered_api_surface():
    from app.main import create_app

    background_paths = {getattr(route, "path", "") for route in create_app("background").routes}
    api_paths = {getattr(route, "path", "") for route in create_app("api").routes}

    assert "/health" in background_paths
    assert not any(path.startswith("/api/v1") for path in background_paths)
    assert "/api/v1/status" in api_paths


def test_frontend_generated_contracts_are_current():
    from scripts import generate_frontend_contracts as generator

    grouped_models = defaultdict(list)
    grouped_query_params = defaultdict(list)
    for contract in generator.collect_route_contract_models():
        grouped_models[contract.target_file].append(contract.model)
    for contract in generator.collect_route_query_param_contracts():
        grouped_query_params[contract.target_file].append(contract)

    changed = []
    for filename in generator.TARGET_FILES:
        expected = generator.render_file(
            grouped_models.get(filename, []),
            grouped_query_params.get(filename, []),
        )
        actual = generator.TARGET_PATHS[filename].read_text(encoding="utf-8")
        if actual != expected:
            changed.append(str(generator.TARGET_PATHS[filename].relative_to(ROOT_DIR)))
    expected_routes = generator.render_api_routes()
    actual_routes = (generator.FRONTEND_API_DIR / "routes.ts").read_text(encoding="utf-8")
    if actual_routes != expected_routes:
        changed.append(str((generator.FRONTEND_API_DIR / "routes.ts").relative_to(ROOT_DIR)))

    assert changed == []


def make_background_runtime_services() -> AppRuntimeServices:
    return AppRuntimeServices.from_entries({
        INFRA_EXCHANGE_GATEWAY: object(),
        INFRA_DATABASE_RUNTIME: object(),
        INFRA_KLINE_STORE: object(),
        INFRA_CACHE_SERVICE: object(),
        MARKET_MARKET_DATA_SERVICE: object(),
        MARKET_INDICATOR_REPOSITORY: object(),
        MARKET_DLI_CACHE: object(),
        MARKET_FUNDING_RATE_STORE: object(),
        MARKET_BINANCE_MARKET_SNAPSHOT: object(),
        MARKET_BINANCE_MARKET_RESEARCH_STORE: object(),
        MARKET_BINANCE_MARKET_INTEL: object(),
        BACKTEST_RUN_REPOSITORY: object(),
        BACKTEST_RUN_WRITER: object(),
        BACKTEST_FACTOR_RUN_WRITER: object(),
        BACKTEST_PAPER_RUN_WRITER: object(),
        BACKTEST_FACTOR_PAPER_RUN_WRITER: object(),
        BACKTEST_FREQTRADE_SERVICE: object(),
        BACKTEST_STRATEGY_DEFINITION_STORE: object(),
        BACKTEST_STRATEGY_QUERY_SERVICE: object(),
        BACKTEST_REPORT_BUILDER: object(),
        BACKTEST_PAPER_RUN_MANAGER: object(),
        FACTORS_RESEARCH_REPOSITORY: object(),
        FACTORS_RESEARCH_SERVICE: object(),
        FACTORS_SIGNAL_EXECUTION_CORE: object(),
        FACTORS_PAPER_PERSISTENCE_SERVICE: object(),
        FACTORS_PAPER_RUN_MANAGER: object(),
        SYSTEM_MARKET_SCHEDULER_RUNTIME: object(),
    })


def make_api_runtime_services() -> AppRuntimeServices:
    return AppRuntimeServices.from_entries({
        INFRA_EXCHANGE_GATEWAY: object(),
        INFRA_DATABASE_RUNTIME: object(),
        INFRA_KLINE_STORE: object(),
        INFRA_CACHE_SERVICE: object(),
        MARKET_MARKET_DATA_SERVICE: object(),
        MARKET_REALTIME_SERVICE: object(),
        MARKET_INDICATOR_REPOSITORY: object(),
        MARKET_DLI_CACHE: object(),
        MARKET_INDICATOR_SERVICE: object(),
        MARKET_FUNDING_RATE_STORE: object(),
        MARKET_FUNDING_RATE_SERVICE: object(),
        MARKET_FUNDING_RATE_APP_SERVICE: object(),
        MARKET_QUERY_APP_SERVICE: object(),
        MARKET_INSIGHT_APP_SERVICE: object(),
        MARKET_WEBSOCKET_SERVICE: object(),
        MARKET_INDEX_DATA_SERVICE: object(),
        MARKET_BINANCE_MARKET_SNAPSHOT: object(),
        MARKET_BINANCE_MARKET_RESEARCH_STORE: object(),
        MARKET_BINANCE_MARKET_INTEL: object(),
        MARKET_BINANCE_WEB3_RANKS: object(),
        MARKET_BINANCE_WEB3_HEAT_RANKS: object(),
        MARKET_BINANCE_WEB3_TOKENS: object(),
        TOOLS_SENTIMENT_API_CLIENT: object(),
        TOOLS_SENTIMENT_REPOSITORY: object(),
        TOOLS_SENTIMENT_SERVICE: object(),
        TOOLS_DCA_SERVICE: object(),
        TOOLS_PAIR_COMPARE_SERVICE: object(),
        TOOLS_TOOLS_APP_SERVICE: object(),
        BACKTEST_RUN_REPOSITORY: object(),
        BACKTEST_RUN_WRITER: object(),
        BACKTEST_FACTOR_RUN_WRITER: object(),
        BACKTEST_PAPER_RUN_WRITER: object(),
        BACKTEST_FACTOR_PAPER_RUN_WRITER: object(),
        BACKTEST_FREQTRADE_SERVICE: object(),
        BACKTEST_PREVIEW_ARTIFACT_STORE: object(),
        BACKTEST_PREVIEW_SERVICE: object(),
        BACKTEST_RUN_SERVICE: object(),
        BACKTEST_STRATEGY_DEFINITION_STORE: object(),
        BACKTEST_STRATEGY_QUERY_SERVICE: object(),
        BACKTEST_STRATEGY_WRITE_SERVICE: object(),
        BACKTEST_REPORT_BUILDER: object(),
        BACKTEST_PAPER_RUN_MANAGER: object(),
        BACKTEST_COMMAND_SERVICE: object(),
        BACKTEST_QUERY_SERVICE: object(),
        FACTORS_RESEARCH_REPOSITORY: object(),
        FACTORS_RESEARCH_SERVICE: object(),
        FACTORS_EXECUTION_SERVICE: object(),
        FACTORS_SIGNAL_EXECUTION_CORE: object(),
        FACTORS_PAPER_PERSISTENCE_SERVICE: object(),
        FACTORS_PAPER_RUN_MANAGER: object(),
        SYSTEM_CURRENCY_RATE_SERVICE: object(),
        SYSTEM_LLM_CONFIG_SERVICE: object(),
        SYSTEM_FRED_API_CONFIG_SERVICE: object(),
    })


def test_background_role_validation_ignores_api_only_graph():
    services = make_background_runtime_services()

    validate_runtime_services(services, "background")
    with pytest.raises(RuntimeError, match="market.realtime_service"):
        validate_runtime_services(services, "api")


def test_api_role_validation_ignores_background_only_graph():
    services = make_api_runtime_services()

    validate_runtime_services(services, "api")
    with pytest.raises(RuntimeError, match="system.market_scheduler_runtime"):
        validate_runtime_services(services, "background")
