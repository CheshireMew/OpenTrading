from __future__ import annotations

from app.contracts.strategy import (
    StrategyConditionNodeResponse,
    StrategyGroupNodeResponse,
    StrategyRuleSourceResponse,
    StrategyTemplateConfigResponse,
)
from app.domain.backtest.strategy_config_normalizer import normalize_strategy_identifier
from app.domain.backtest.strategy_rule_tree import strategy_branch


class FreqtradeRuleCodegen:
    def build_branch_masks(
        self,
        normalized_config: StrategyTemplateConfigResponse,
        regime_priority: list[str],
    ) -> dict[str, str]:
        masks: dict[str, str] = {}
        remaining = '(dataframe["volume"] >= 0)'
        false_mask = '(dataframe["volume"] < 0)'
        for branch_key in regime_priority:
            branch = strategy_branch(normalized_config, branch_key)
            if not branch.enabled:
                masks[branch_key] = false_mask
                continue
            regime_mask = self.compile_rule_tree(branch.regime)
            active_mask = f"(({remaining}) & ({regime_mask}))"
            masks[branch_key] = active_mask
            remaining = f"(({remaining}) & ~({active_mask}))"
        return masks

    def build_signal_assignments(
        self,
        normalized_config: StrategyTemplateConfigResponse,
        regime_priority: list[str],
        branch_masks: dict[str, str],
        *,
        signal_kind: str,
        can_short: bool,
    ) -> str:
        lines: list[str] = []
        if signal_kind == "entry":
            lines.append('        dataframe["enter_short"] = 0')
            lines.append('        dataframe["enter_short_tag"] = None')
        else:
            lines.append('        dataframe["exit_short"] = 0')
            lines.append('        dataframe["exit_short_tag"] = None')
        for branch_key in regime_priority:
            branch = strategy_branch(normalized_config, branch_key)
            if not branch.enabled:
                continue
            long_tree = branch.long_entry if signal_kind == "entry" else branch.long_exit
            long_column = "enter_long" if signal_kind == "entry" else "exit_long"
            long_tag = "enter_tag" if signal_kind == "entry" else "exit_tag"
            if self._signal_tree_enabled(long_tree):
                long_condition = f"(({branch_masks[branch_key]}) & ({self.compile_rule_tree(long_tree)}))"
                lines.append(f'        dataframe.loc[{long_condition}, ["{long_column}", "{long_tag}"]] = (1, "{branch_key}_long_{signal_kind}")')
            if not can_short:
                continue
            short_tree = branch.short_entry if signal_kind == "entry" else branch.short_exit
            short_column = "enter_short" if signal_kind == "entry" else "exit_short"
            short_tag = "enter_short_tag" if signal_kind == "entry" else "exit_short_tag"
            shared_tag = "enter_tag" if signal_kind == "entry" else "exit_tag"
            if self._signal_tree_enabled(short_tree):
                short_condition = f"(({branch_masks[branch_key]}) & ({self.compile_rule_tree(short_tree)}))"
                lines.append(
                    f'        dataframe.loc[{short_condition}, ["{short_column}", "{short_tag}", "{shared_tag}"]] = '
                    f'(1, "{branch_key}_short_{signal_kind}", "{branch_key}_short_{signal_kind}")'
                )
        if not can_short:
            if signal_kind == "entry":
                lines = ['        dataframe["enter_short"] = 0', '        dataframe["enter_short_tag"] = None', *lines[2:]]
            else:
                lines = ['        dataframe["exit_short"] = 0', '        dataframe["exit_short_tag"] = None', *lines[2:]]
        return "\n".join(lines) if lines else "        pass"

    def build_exit_assignments(
        self,
        normalized_config: StrategyTemplateConfigResponse,
        regime_priority: list[str],
        branch_masks: dict[str, str],
        *,
        can_short: bool,
        uses_trade_plan: bool,
    ) -> str:
        if not uses_trade_plan:
            return self.build_signal_assignments(
                normalized_config,
                regime_priority,
                branch_masks,
                signal_kind="exit",
                can_short=can_short,
            )
        return "\n".join([
            '        dataframe["exit_short"] = 0',
            '        dataframe["exit_short_tag"] = None',
        ])

    def compile_rule_tree(self, node: StrategyGroupNodeResponse | StrategyConditionNodeResponse) -> str:
        if not node.enabled:
            return '(dataframe["volume"] >= 0)'
        if isinstance(node, StrategyConditionNodeResponse):
            return self._compile_single_rule(node)
        enabled_children = [child for child in node.children if child.enabled]
        if not enabled_children:
            return '(dataframe["volume"] >= 0)'
        glue = " & " if node.logic == "and" else " | "
        return "(" + glue.join(self.compile_rule_tree(child) for child in enabled_children) + ")"

    def _compile_single_rule(self, rule: StrategyConditionNodeResponse) -> str:
        operator_map = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        operator = operator_map.get(rule.operator)
        if not operator:
            raise ValueError(f"不支持的条件操作符: {rule.operator}")
        return f"({self._compile_source(rule.left)} {operator} {self._compile_source(rule.right)})"

    def _compile_source(self, source: StrategyRuleSourceResponse) -> str:
        kind = source.kind
        bars_ago = max(int(source.bars_ago or 0), 0)
        if kind == "price":
            expression = f'dataframe["{source.field or "close"}"]'
            return self._apply_shift(expression, bars_ago)
        if kind == "indicator":
            normalize_strategy_identifier(source.indicator, "指标标识")
            normalize_strategy_identifier(source.output or "value", "指标输出")
            expression = f'dataframe["{source.indicator}__{source.output or "value"}"]'
            return self._apply_shift(expression, bars_ago)
        if kind == "value":
            return repr(float(source.value or 0))
        if kind == "indicator_multiplier":
            normalize_strategy_identifier(source.indicator, "指标标识")
            normalize_strategy_identifier(source.output or "value", "指标输出")
            expression = f'(dataframe["{source.indicator}__{source.output or "value"}"] * {float(source.multiplier or 1.0)})'
            return self._apply_shift(expression, bars_ago)
        if kind == "indicator_offset":
            normalize_strategy_identifier(source.base_indicator, "基础指标标识")
            normalize_strategy_identifier(source.base_output or "value", "基础指标输出")
            normalize_strategy_identifier(source.offset_indicator, "偏移指标标识")
            normalize_strategy_identifier(source.offset_output or "value", "偏移指标输出")
            expression = (
                f'(dataframe["{source.base_indicator}__{source.base_output or "value"}"] '
                f'- dataframe["{source.offset_indicator}__{source.offset_output or "value"}"] * {float(source.offset_multiplier or 1.0)})'
            )
            return self._apply_shift(expression, bars_ago)
        raise ValueError(f"不支持的条件源: {kind}")

    @staticmethod
    def _apply_shift(expression: str, bars_ago: int) -> str:
        if bars_ago <= 0:
            return expression
        return f"({expression}).shift({bars_ago})"

    @staticmethod
    def _signal_tree_enabled(node: StrategyGroupNodeResponse | StrategyConditionNodeResponse) -> bool:
        if not node.enabled:
            return False
        if isinstance(node, StrategyGroupNodeResponse):
            return any(child.enabled for child in node.children)
        return True
