from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.contracts.backtest import EvolveStrategyFromBacktestCommand
from app.contracts.backtest_result import (
    BacktestReportResponse,
    BacktestReportSnapshotResponse,
    BacktestResearchReportResponse,
)
from app.application.backtest.ports import BacktestRunReader, StrategyReader, StrategyWriter
from app.domain.backtest.scripted_templates import template_supports_version_editing
from app.domain.backtest.strategy_catalog import get_template_runtime_contract
from app.domain.backtest.strategy_support import (
    build_strategy_version_response_payload,
    normalize_strategy_version_config_model,
)


EvolutionDefect = dict[str, Any]
EvolutionChange = dict[str, Any]


class StrategyEvolutionService:
    """Diagnose a completed backtest and persist an evolved strategy version."""

    def __init__(
        self,
        *,
        run_repository: BacktestRunReader,
        strategy_query_service: StrategyReader,
        strategy_write_service: StrategyWriter,
    ) -> None:
        self.run_repository = run_repository
        self.strategy_query_service = strategy_query_service
        self.strategy_write_service = strategy_write_service

    def evolve_from_backtest(
        self, command: EvolveStrategyFromBacktestCommand
    ) -> dict:
        backtest_id = command.require_backtest_id()
        run = self.run_repository.get_run(backtest_id, page=1, page_size=1000, execution_mode="backtest")
        if run is None:
            raise ValueError(f"回测记录不存在: {backtest_id}")
        if run.get("status") != "completed":
            raise ValueError("只有已完成的回测才能用于策略进化")
        report_payload = run.get("report")
        if report_payload is None:
            raise ValueError("回测缺少绩效报告，无法诊断策略缺陷")
        report = BacktestReportResponse.model_validate(report_payload)
        metadata = run.get("metadata") or {}

        strategy_key = _strategy_key(report, metadata)
        source_version = _strategy_version(report, metadata)
        if not strategy_key:
            raise ValueError("回测缺少策略标识，无法创建进化版本")

        source_strategy = self.strategy_query_service.get_strategy_version(strategy_key, source_version)
        runtime_contract = get_template_runtime_contract(source_strategy.template)
        if not template_supports_version_editing(runtime_contract):
            raise ValueError("当前策略是只读脚本策略，不能自动创建进化版本")

        base_config = _selected_config(report) or _metadata_selected_config(metadata) or source_strategy.config
        normalized_base = normalize_strategy_version_config_model(
            source_strategy.template,
            base_config,
        ).model_dump()
        defects = diagnose_strategy_defects(report)
        evolved_config, changes = evolve_strategy_config(report, normalized_base)
        normalized_evolved = normalize_strategy_version_config_model(
            source_strategy.template,
            evolved_config,
        )

        created_version = None
        created = False
        if changes and not command.dry_run:
            definition = self._strategy_definition(strategy_key)
            result = self.strategy_write_service.create_strategy_version(
                key=strategy_key,
                name=command.version_name or f"{source_strategy.strategy_name} evolved from run #{run['id']}",
                template=source_strategy.template,
                category=definition.get("category") or "custom",
                description=definition.get("description") or source_strategy.description,
                config=normalized_evolved.model_dump(),
                parameter_space=source_strategy.parameter_space,
                notes=command.notes or _default_evolution_notes(run["id"], defects, changes),
                make_default=command.make_default,
            )
            created_version = build_strategy_version_response_payload(result)
            created = True

        message = _evolution_message(created=created, dry_run=command.dry_run, changes=changes, defects=defects)
        return {
            "source_backtest_id": run["id"],
            "strategy_key": strategy_key,
            "source_version": source_version,
            "created": created,
            "message": message,
            "defects": defects,
            "changes": changes,
            "evolved_version": created_version,
            "base_config": normalize_strategy_version_config_model(
                source_strategy.template,
                normalized_base,
            ),
            "evolved_config": normalized_evolved,
        }

    def _strategy_definition(self, strategy_key: str) -> dict[str, Any]:
        for definition in self.strategy_query_service.list_strategies():
            if definition.get("key") == strategy_key:
                return definition
        return {}


def diagnose_strategy_defects(report: BacktestReportResponse) -> list[EvolutionDefect]:
    defects: list[EvolutionDefect] = []
    if report.total_trades <= 0:
        defects.append(
            _defect(
                "entry_starvation",
                "critical",
                "没有产生交易",
                [f"total_trades={report.total_trades}"],
                "入场条件过窄或状态过滤没有覆盖样本，先扩大参数搜索空间或检查入场分支。",
            )
        )

    if report.profit_pct < 0:
        defects.append(
            _defect(
                "negative_expectancy",
                "critical",
                "策略期望为负",
                [f"profit_pct={report.profit_pct:.2f}%"],
                "优先使用样本内优化胜出的参数；没有优化结果时先收紧风险暴露。",
            )
        )

    if report.total_trades >= 5 and report.win_rate < 35:
        defects.append(
            _defect(
                "low_win_rate",
                "warning",
                "胜率过低",
                [f"win_rate={report.win_rate:.2f}%", f"total_trades={report.total_trades}"],
                "检查入场确认条件和离场条件是否把噪声交易放大。",
            )
        )

    if report.profit_factor is not None and report.profit_factor < 1:
        defects.append(
            _defect(
                "poor_profit_factor",
                "critical",
                "盈亏比不足",
                [f"profit_factor={report.profit_factor:.2f}"],
                "降低单笔亏损上限，保留优化结果中更高 profit_factor 的参数。",
            )
        )

    drawdown = abs(report.max_drawdown_pct)
    if drawdown >= 25:
        defects.append(
            _defect(
                "excessive_drawdown",
                "critical",
                "最大回撤过高",
                [f"max_drawdown_pct={report.max_drawdown_pct:.2f}%"],
                "收紧止损并启用追踪止损，避免单轮亏损拖垮整段样本。",
            )
        )
    elif drawdown >= 12:
        defects.append(
            _defect(
                "elevated_drawdown",
                "warning",
                "最大回撤偏高",
                [f"max_drawdown_pct={report.max_drawdown_pct:.2f}%"],
                "用更小的止损暴露和追踪止损降低回撤尾部。",
            )
        )

    research = report.research
    if research is not None:
        defects.extend(_diagnose_sample_split(research))
        defects.extend(_diagnose_rolling_windows(research))
        if research.optimization and research.optimization.best_config:
            defects.append(
                _defect(
                    "optimizable_version_available",
                    "info",
                    "已有更优候选参数",
                    [
                        f"metric={research.optimization.metric}",
                        f"best_score={_format_optional_number(research.optimization.best_score)}",
                    ],
                    "将优化胜出的配置固化为新的策略版本，避免只停留在临时回测配置。",
                )
            )

    losing_pairs = [
        item for item in report.pair_breakdown if item.profit_pct < 0
    ]
    if losing_pairs:
        evidence = [
            f"{item.pair}: {item.profit_pct:.2f}%"
            for item in sorted(losing_pairs, key=lambda value: value.profit_pct)[:3]
        ]
        defects.append(
            _defect(
                "pair_fragility",
                "warning",
                "部分交易对拖累组合",
                evidence,
                "复核组合标的，必要时分策略或分市场类型维护参数。",
            )
        )

    if not defects:
        defects.append(
            _defect(
                "no_material_defect",
                "info",
                "未发现需要自动进化的明显缺陷",
                ["核心收益、回撤和样本稳定性没有触发阈值"],
                "继续用滚动窗口和模拟盘累积样本，不强行改写策略。",
            )
        )
    return defects


def evolve_strategy_config(
    report: BacktestReportResponse,
    base_config: dict[str, Any],
) -> tuple[dict[str, Any], list[EvolutionChange]]:
    optimization_best = None
    if report.research and report.research.optimization and report.research.optimization.best_config:
        optimization_best = report.research.optimization.best_config.model_dump()

    if optimization_best:
        evolved = deepcopy(optimization_best)
        changes = _diff_scalar_changes(base_config, evolved)
        if changes:
            return evolved, [
                _change(item["path"], item["before"], item["after"], "采用参数优化中胜出的候选配置")
                for item in changes
            ]

    evolved = deepcopy(base_config)
    changes: list[EvolutionChange] = []
    drawdown = abs(report.max_drawdown_pct)
    risk = evolved.setdefault("risk", {})

    if report.profit_pct < 0 or drawdown >= 12 or (report.profit_factor is not None and report.profit_factor < 1):
        current_stoploss = float(risk.get("stoploss", -0.10) or -0.10)
        target_stoploss = -min(max(abs(current_stoploss) * 0.75, 0.01), 0.25)
        if round(target_stoploss, 6) != round(current_stoploss, 6):
            risk["stoploss"] = target_stoploss
            changes.append(
                _change("risk.stoploss", current_stoploss, target_stoploss, "回撤或负收益触发风险收紧")
            )

    if drawdown >= 12:
        trailing = risk.setdefault("trailing", {})
        if trailing.get("enabled") is not True:
            trailing["enabled"] = True
            changes.append(
                _change("risk.trailing.enabled", False, True, "最大回撤偏高，启用追踪止损")
            )
        positive = float(trailing.get("positive", 0.02) or 0.02)
        offset = float(trailing.get("offset", 0.03) or 0.03)
        target_positive = min(max(positive, 0.01), 0.03)
        target_offset = min(max(offset, target_positive + 0.01), 0.05)
        if round(target_positive, 6) != round(positive, 6):
            trailing["positive"] = target_positive
            changes.append(
                _change("risk.trailing.positive", positive, target_positive, "统一追踪止损触发阈值")
            )
        if round(target_offset, 6) != round(offset, 6):
            trailing["offset"] = target_offset
            changes.append(
                _change("risk.trailing.offset", offset, target_offset, "统一追踪止损回撤偏移")
            )

    return evolved, changes


def _diagnose_sample_split(research: BacktestResearchReportResponse) -> list[EvolutionDefect]:
    if not research.in_sample or not research.out_of_sample:
        return []
    in_report = research.in_sample.report
    out_report = research.out_of_sample.report
    if not in_report or not out_report:
        return []
    in_profit = in_report.profit_pct
    out_profit = out_report.profit_pct
    if in_profit is None or out_profit is None:
        return []
    if in_profit > 0 and out_profit < 0:
        return [
            _defect(
                "overfit_sample_split",
                "critical",
                "样本外失效",
                [f"in_sample={in_profit:.2f}%", f"out_of_sample={out_profit:.2f}%"],
                "不要直接信任单段最优参数，优先降低复杂度并用滚动窗口复核。",
            )
        ]
    if in_profit - out_profit >= 15:
        return [
            _defect(
                "sample_decay",
                "warning",
                "样本外收益明显衰减",
                [f"in_sample={in_profit:.2f}%", f"out_of_sample={out_profit:.2f}%"],
                "把进化候选约束在滚动窗口稳定的参数上。",
            )
        ]
    return []


def _diagnose_rolling_windows(research: BacktestResearchReportResponse) -> list[EvolutionDefect]:
    windows = [item for item in research.rolling_windows if item.report is not None]
    if len(windows) < 2:
        return []
    losing = [item for item in windows if (item.report.profit_pct or 0) < 0]
    if len(losing) / len(windows) >= 0.4:
        return [
            _defect(
                "rolling_instability",
                "critical",
                "滚动窗口不稳定",
                [f"losing_windows={len(losing)}/{len(windows)}"],
                "降低参数对单一行情段的依赖，保留跨窗口更稳的候选配置。",
            )
        ]
    return []


def _defect(
    key: str,
    severity: str,
    title: str,
    evidence: list[str],
    recommendation: str,
) -> EvolutionDefect:
    return {
        "key": key,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _change(path: str, before: Any, after: Any, reason: str) -> EvolutionChange:
    return {
        "path": path,
        "before": before,
        "after": after,
        "reason": reason,
    }


def _diff_scalar_changes(
    before: Any,
    after: Any,
    path: str = "",
) -> list[EvolutionChange]:
    changes: list[EvolutionChange] = []
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(set(before) | set(after))
        for key in keys:
            current_path = f"{path}.{key}" if path else key
            changes.extend(_diff_scalar_changes(before.get(key), after.get(key), current_path))
        return changes
    if isinstance(before, list) and isinstance(after, list):
        max_length = max(len(before), len(after))
        for index in range(max_length):
            left = before[index] if index < len(before) else None
            right = after[index] if index < len(after) else None
            changes.extend(_diff_scalar_changes(left, right, f"{path}[{index}]"))
        return changes
    if before != after and _is_json_change_value(before) and _is_json_change_value(after):
        changes.append(_change(path, before, after, "参数发生变化"))
    return changes


def _is_json_change_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(item is None or isinstance(item, (str, int, float, bool)) for item in value)
    return False


def _strategy_key(report: BacktestReportResponse, metadata: Any) -> str:
    if report.strategy and report.strategy.key:
        return report.strategy.key
    if isinstance(metadata, dict):
        return str(metadata.get("strategy_key") or "")
    return str(getattr(metadata, "strategy_key", "") or "")


def _strategy_version(report: BacktestReportResponse, metadata: Any) -> int | None:
    if report.strategy and report.strategy.version:
        return report.strategy.version
    value = metadata.get("strategy_version") if isinstance(metadata, dict) else getattr(metadata, "strategy_version", None)
    return int(value) if value is not None else None


def _selected_config(report: BacktestReportResponse) -> dict[str, Any] | None:
    if report.research and report.research.selected_config:
        return report.research.selected_config.model_dump()
    return None


def _metadata_selected_config(metadata: Any) -> dict[str, Any] | None:
    value = metadata.get("selected_config") if isinstance(metadata, dict) else getattr(metadata, "selected_config", None)
    return dict(value) if isinstance(value, dict) and value else None


def _default_evolution_notes(
    run_id: int,
    defects: list[EvolutionDefect],
    changes: list[EvolutionChange],
) -> str:
    defect_titles = "、".join(item["title"] for item in defects if item["severity"] != "info") or "未发现重大缺陷"
    change_paths = "、".join(item["path"] for item in changes[:6])
    return f"由回测 #{run_id} 自动诊断进化。缺陷: {defect_titles}。变更: {change_paths}。"


def _evolution_message(
    *,
    created: bool,
    dry_run: bool,
    changes: list[EvolutionChange],
    defects: list[EvolutionDefect],
) -> str:
    if dry_run and changes:
        return "已完成缺陷诊断和进化预演，未创建新版本"
    if created:
        return "已完成缺陷诊断，并创建新的策略版本"
    if not changes and any(item["key"] == "entry_starvation" for item in defects):
        return "已发现缺陷，但缺少可安全自动迁移的参数变化；请先补充参数搜索空间"
    return "已完成缺陷诊断，当前没有需要自动创建的新版本"


def _format_optional_number(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"
