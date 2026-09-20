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
        if spec.options and not any(type(value) is type(o.value) and value == o.value for o in spec.options):
            raise ValueError(f"参数 {name} 必须选择已声明的选项")
        result[name] = value
    for name, spec in metadata.parameters.items():
        for condition in spec.enabled_when:
            if condition.parameter not in result:
                raise ValueError(f'参数 {name} 的生效条件引用了未知参数 {condition.parameter}')
    for constraint in metadata.parameter_constraints:
        if not conditions_match(constraint.enabled_when, result):
            continue
        if constraint.parameter not in result or constraint.other_parameter and constraint.other_parameter not in result:
            raise ValueError('参数约束引用了未知字段')
        actual = result[constraint.parameter]
        other = result[constraint.other_parameter] if constraint.other_parameter else constraint.value
        passed = {'lt': lambda: actual < other, 'le': lambda: actual <= other,
                  'eq': lambda: actual == other, 'gt': lambda: actual > other,
                  'integer': lambda: not isinstance(actual, bool) and float(actual).is_integer()}[constraint.operator]()
        if not passed:
            raise ValueError(constraint.message)
    return result


def conditions_match(conditions, values):
    for c in conditions:
        if c.parameter not in values:
            raise ValueError(f'条件引用了未知参数 {c.parameter}')
        actual = values[c.parameter]
        if not {'eq': lambda: actual == c.value, 'ne': lambda: actual != c.value,
                'in': lambda: actual in c.value, 'gt': lambda: actual > c.value}[c.operator]():
            return False
    return True


def resolve_warmup(metadata, values):
    rule = metadata.warmup_rule
    if rule is None:
        return metadata.warmup_bars, '该保存版本采用固定预热根数；未声明参数相关收敛规则。'
    lengths = [rule.minimum_bars]
    for term in rule.terms:
        if not conditions_match(term.enabled_when, values):
            continue
        period = values.get(term.period) if isinstance(term.period, str) else term.period
        if isinstance(period, bool) or not isinstance(period, (int, float)) or period < 1 or not float(period).is_integer():
            raise ValueError(f'预热周期必须为正整数：{term.period}')
        period = int(period)
        if term.kind == 'window':
            count = period
        else:
            alpha = 2 / (period + 1) if term.kind == 'ema' else 1 / period
            updates = 0 if alpha == 1 else math.ceil(math.log(rule.seed_weight_tolerance) / math.log1p(-alpha))
            count = (1 if term.kind == 'ema' else period) + updates
        extra = values.get(term.extra_bars) if isinstance(term.extra_bars, str) else term.extra_bars
        if isinstance(extra, bool) or not isinstance(extra, int) or extra < 0:
            raise ValueError('预热附加窗口必须为非负整数')
        lengths.append(count + extra)
    return max(lengths), rule.explanation


def rules_summary(metadata, values):
    result = list(metadata.rules) or [metadata.description]
    parts = []
    for name, spec in metadata.parameters.items():
        if not conditions_match(spec.enabled_when, values):
            continue
        value = values[name]
        label = next((o.label for o in spec.options if type(o.value) is type(value) and o.value == value), None)
        text = label if label is not None else ('开启' if value else '关闭') if isinstance(value, bool) else str(value)
        label = spec.label or name
        parts.append(f'{label}：{text}{(" " + spec.unit) if spec.unit and spec.unit not in label else ""}')
    return result + ['；'.join(parts)]
