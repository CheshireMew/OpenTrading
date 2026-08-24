from __future__ import annotations

from typing import Any

import pandas as pd

from app.contracts.strategy import (
    StrategyConditionNodeResponse,
    StrategyGroupNodeResponse,
    StrategyRuleSourceResponse,
    StrategyTemplateConfigResponse,
)
from app.domain.backtest.strategy_rule_tree import strategy_branch


class StrategyRuleEvaluator:
    def evaluate_rule_tree(
        self,
        frame: pd.DataFrame,
        node: StrategyGroupNodeResponse | StrategyConditionNodeResponse,
    ) -> pd.Series:
        if not node.enabled:
            return pd.Series(True, index=frame.index, dtype=bool)
        if isinstance(node, StrategyConditionNodeResponse):
            return self._evaluate_condition(frame, node)
        logic = node.logic
        children = [child for child in node.children if child.enabled]
        if not children:
            return pd.Series(True, index=frame.index, dtype=bool)
        evaluated = [self.evaluate_rule_tree(frame, child) for child in children]
        result = evaluated[0]
        for item in evaluated[1:]:
            result = result & item if logic == "and" else result | item
        return result.fillna(False)

    def evaluate_signal_rule_tree(
        self,
        frame: pd.DataFrame,
        node: StrategyGroupNodeResponse | StrategyConditionNodeResponse,
    ) -> pd.Series:
        if not node.enabled:
            return pd.Series(False, index=frame.index, dtype=bool)
        if isinstance(node, StrategyGroupNodeResponse) and not [child for child in node.children if child.enabled]:
            return pd.Series(False, index=frame.index, dtype=bool)
        return self.evaluate_rule_tree(frame, node)

    def resolve_branch_masks(self, frame: pd.DataFrame, config: StrategyTemplateConfigResponse) -> dict[str, pd.Series]:
        remaining = pd.Series(True, index=frame.index, dtype=bool)
        masks: dict[str, pd.Series] = {}
        for branch_key in config.regime_priority or ["trend", "range"]:
            branch = strategy_branch(config, branch_key)
            if not branch.enabled:
                masks[branch_key] = pd.Series(False, index=frame.index, dtype=bool)
                continue
            regime_mask = self.evaluate_rule_tree(frame, branch.regime)
            active_mask = (remaining & regime_mask).fillna(False)
            masks[branch_key] = active_mask
            remaining = (remaining & ~active_mask).fillna(False)
        return masks

    def _evaluate_condition(self, frame: pd.DataFrame, node: StrategyConditionNodeResponse) -> pd.Series:
        left = self._resolve_source(frame, node.left)
        right = self._resolve_source(frame, node.right)
        operator = node.operator
        if operator == "gt":
            return (left > right).fillna(False)
        if operator == "gte":
            return (left >= right).fillna(False)
        if operator == "lt":
            return (left < right).fillna(False)
        if operator == "lte":
            return (left <= right).fillna(False)
        raise ValueError(f"不支持的条件操作符: {operator}")

    def _resolve_source(self, frame: pd.DataFrame, source: StrategyRuleSourceResponse) -> pd.Series:
        kind = source.kind
        bars_ago = max(int(source.bars_ago or 0), 0)
        if kind == "price":
            field = source.field or "close"
            return frame[field].shift(bars_ago)
        if kind == "indicator":
            return frame[f"{source.indicator}__{source.output or 'value'}"].shift(bars_ago)
        if kind == "value":
            return pd.Series(float(source.value or 0), index=frame.index, dtype=float)
        if kind == "indicator_multiplier":
            base = frame[f"{source.indicator}__{source.output or 'value'}"]
            return (base * float(source.multiplier or 1.0)).shift(bars_ago)
        if kind == "indicator_offset":
            base = frame[f"{source.base_indicator}__{source.base_output or 'value'}"]
            offset = frame[f"{source.offset_indicator}__{source.offset_output or 'value'}"]
            return (base - (offset * float(source.offset_multiplier or 1.0))).shift(bars_ago)
        raise ValueError(f"不支持的条件源: {kind}")
