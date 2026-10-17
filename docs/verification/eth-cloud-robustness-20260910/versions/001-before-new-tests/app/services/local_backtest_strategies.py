from __future__ import annotations
import hashlib
import ast
import importlib.metadata
import math
import sys
from pathlib import Path
from types import ModuleType

from app.contracts.local_backtest import LocalBacktestStrategy
from app.domain.local_backtest import ENGINE_VERSION
from config.settings import BASE_DIR

STRATEGIES_DIR = BASE_DIR / "strategies"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def environment():
    return {"engine": ENGINE_VERSION, "python": sys.version.split()[0],
            "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "TA-Lib")}}


def load_strategy(path: Path):
    module = ModuleType("heimdall_strategy_" + digest(path.read_bytes())[:16])
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    metadata = LocalBacktestStrategy.model_validate(module.STRATEGY)
    if metadata.api_version != "1" or metadata.warmup_bars < 0 or not callable(getattr(module, "on_bar", None)):
        raise ValueError(f"策略接口或预热定义无效：{path.name}")
    return module, metadata


def inspect_strategy(source: bytes, filename: str):
    """Read metadata without executing user code in the API process."""
    try:
        tree = ast.parse(source.decode("utf-8-sig"), filename=filename)
    except (SyntaxError, UnicodeError) as exc:
        raise ValueError(f"策略 {filename} 无法解析：{exc}") from exc
    value = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STRATEGY" for t in node.targets):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "STRATEGY":
            value = node.value
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "dict" and not value.args:
        if any(kw.arg is None for kw in value.keywords):
            raise ValueError("STRATEGY 不支持动态展开，请使用静态字典")
        payload = {kw.arg: ast.literal_eval(kw.value) for kw in value.keywords if kw.arg is not None}
    else:
        try:
            payload = ast.literal_eval(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("STRATEGY 必须是静态字典，不能通过运行代码生成") from exc
    metadata = LocalBacktestStrategy.model_validate(payload)
    if metadata.api_version != "1" or metadata.warmup_bars < 0:
        raise ValueError("策略接口版本或预热定义无效")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "on_bar" for n in tree.body):
        raise ValueError("策略必须定义同步函数 on_bar(context)")
    for node in ast.walk(tree):
        imports = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        for name in imports:
            root = name.split(".")[0]
            if (isinstance(node, ast.ImportFrom) and node.level) or (root not in sys.stdlib_module_names | {"numpy", "pandas", "talib"} and name != "app.domain.local_backtest"):
                raise ValueError(f"不支持未快照化的辅助模块：{name}；请使用单文件策略与公开接口")
    validate_parameters(metadata, {})
    return metadata


def strategy_path(identifier: str):
    if not identifier or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in identifier):
        raise ValueError("无效策略标识")
    path = STRATEGIES_DIR / f"{identifier}.py"
    if not path.is_file():
        raise ValueError(f"策略不存在：{identifier}")
    return path


def validate_parameters(metadata, values):
    unknown = set(values) - set(metadata.parameters)
    if unknown:
        raise ValueError(f"未知策略参数：{sorted(unknown)}")
    result = {}
    for name, spec in metadata.parameters.items():
        value = values.get(name, spec.default)
        expected = {"int": int, "float": (int, float), "bool": bool, "str": str}[spec.type]
        if not isinstance(value, expected) or (spec.type in ("int", "float") and isinstance(value, bool)):
            raise ValueError(f"参数 {name} 类型应为 {spec.type}")
        if spec.type in ("int", "float"):
            if not math.isfinite(value) or (spec.min is not None and value < spec.min) or (spec.max is not None and value > spec.max):
                raise ValueError(f"参数 {name} 超出范围")
        result[name] = value
    return result
