from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_domain_has_no_transport_or_infrastructure_dependencies():
    violations: list[str] = []
    for path in (APP / "domain").rglob("*.py"):
        for module in imported_modules(path):
            if module == "config" or module.startswith((
                "config.",
                "app.contracts",
                "app.infra",
                "app.routers",
                "app.services",
            )):
                violations.append(f"{path.relative_to(ROOT)} -> {module}")
    assert violations == []


def test_infrastructure_has_no_transport_dependencies():
    violations = [
        f"{path.relative_to(ROOT)} -> {module}"
        for path in (APP / "infra").rglob("*.py")
        for module in imported_modules(path)
        if module.startswith(("app.contracts", "app.exceptions", "app.routers", "app.services"))
    ]
    assert violations == []


def test_application_has_no_outer_layer_dependencies():
    violations = [
        f"{path.relative_to(ROOT)} -> {module}"
        for path in (APP / "application").rglob("*.py")
        for module in imported_modules(path)
        if module.startswith(("app.contracts", "app.exceptions", "app.infra", "app.routers", "app.services"))
    ]
    assert violations == []


def test_inner_layers_do_not_import_service_orchestration():
    violations = [
        f"{path.relative_to(ROOT)} -> {module}"
        for layer in ("domain", "application", "infra")
        for path in (APP / layer).rglob("*.py")
        for module in imported_modules(path)
        if module.startswith("app.services")
    ]
    assert violations == []


def test_replaced_architecture_is_absent_from_active_tree():
    retired_paths = (
        APP / "services" / "market" / "kline_range_loader.py",
        APP / "services" / "persistence_ports.py",
        APP / "contracts" / "sentiment.py",
        APP / "domain" / "market" / "timeframes.py",
        ROOT / "utils" / "time_manager.py",
        ROOT / "utils" / "time_utils.py",
        ROOT / "frontend" / "src" / "components" / "HelloWorld.vue",
        ROOT / "frontend" / "src" / "components" / "chartOptions.ts",
    )
    assert [str(path.relative_to(ROOT)) for path in retired_paths if path.exists()] == []


def test_runtime_has_no_string_based_service_locator():
    runtime_text = (APP / "runtime.py").read_text(encoding="utf-8")
    dependencies_text = (APP / "dependencies.py").read_text(encoding="utf-8")
    assert "def require(self, name:" not in runtime_text
    assert "_required_service" not in dependencies_text
