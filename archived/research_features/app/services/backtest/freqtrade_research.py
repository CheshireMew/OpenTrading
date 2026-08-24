from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.contracts.backtest_result import (
    BacktestDateRangeResponse,
    BacktestIterationSummaryResponse,
    BacktestOptimizationSummaryResponse,
    BacktestOptimizationTrialResponse,
    BacktestRollingWindowResponse,
)
from app.contracts.strategy import StrategyTemplateConfigResponse
from app.services.backtest.freqtrade_execution import (
    FreqtradeExecutionContext,
    FreqtradeIterationExecutor,
    IterationResult,
)
from app.domain.backtest.strategy_support import normalize_strategy_version_config_model


class FreqtradeResearchService:
    def __init__(
        self,
        *,
        iteration_executor: FreqtradeIterationExecutor,
        strategy_builder: Any,
        result_builder: Any,
    ) -> None:
        self.iteration_executor = iteration_executor
        self.strategy_builder = strategy_builder
        self.result_builder = result_builder

    def optimize_strategy(
        self,
        *,
        context: FreqtradeExecutionContext,
        base_config: StrategyTemplateConfigResponse,
        optimize_start: datetime,
        optimize_end: datetime,
    ) -> tuple[StrategyTemplateConfigResponse, BacktestOptimizationSummaryResponse, IterationResult]:
        best_score_value = float("-inf")
        best_score = None
        best_iteration = None
        trials = []
        for trial_index, candidate_payload in enumerate(
            self.strategy_builder.candidate_configs(
                base_config.model_dump(),
                context.strategy.parameter_space,
                context.research.optimize_trials,
            ),
            start=1,
        ):
            candidate = normalize_strategy_version_config_model(context.strategy.template, candidate_payload)
            iteration = self.iteration_executor.run_iteration(
                label=f"opt_{trial_index}",
                context=context,
                strategy_config=candidate,
                start_date=optimize_start,
                end_date=optimize_end,
            )
            score = self.result_builder.extract_metric(
                iteration.execution.report,
                context.research.optimize_metric,
            )
            score_value = float("-inf") if score is None else score
            trials.append(
                BacktestOptimizationTrialResponse(
                    trial=trial_index,
                    score=score,
                    config=candidate.model_dump(),
                    report=self.result_builder.report_snapshot(iteration.execution.report),
                )
            )
            if best_iteration is None or score_value > best_score_value:
                best_score_value = score_value
                best_score = score
                best_iteration = iteration

        if best_iteration is None:
            raise RuntimeError("参数优化未产出有效结果")

        return (
            best_iteration.config,
            BacktestOptimizationSummaryResponse(
                metric=context.research.optimize_metric,
                trial_count=len(trials),
                best_score=best_score,
                best_config=best_iteration.config.model_dump(),
                trials=trials,
            ),
            best_iteration,
        )

    def run_rolling_windows(
        self,
        *,
        context: FreqtradeExecutionContext,
        base_config: StrategyTemplateConfigResponse,
        start_date: datetime,
        end_date: datetime,
    ) -> list[BacktestRollingWindowResponse]:
        if context.research.rolling_windows <= 0:
            return []
        results = []
        for index, window in enumerate(
            self.build_rolling_windows(
                start_date,
                end_date,
                context.research.rolling_windows,
                context.research.in_sample_ratio,
            ),
            start=1,
        ):
            window_config = base_config
            optimization = None
            if window["train"] and context.research.optimize_trials > 0 and context.strategy.parameter_space:
                window_config, optimization, _best = self.optimize_strategy(
                    context=context,
                    base_config=window_config,
                    optimize_start=window["train"]["start"],
                    optimize_end=window["train"]["end"],
                )
            result = self.iteration_executor.run_iteration(
                label=f"rolling_{index}",
                context=context,
                strategy_config=window_config,
                start_date=window["test"]["start"],
                end_date=window["test"]["end"],
            )
            results.append(
                BacktestRollingWindowResponse(
                    index=index,
                    train=self.range_payload(window["train"]["start"], window["train"]["end"]) if window["train"] else None,
                    test=self.range_payload(window["test"]["start"], window["test"]["end"]),
                    config=window_config.model_dump(),
                    optimization=optimization,
                    report=self.result_builder.report_snapshot(result.execution.report),
                )
            )
        return results

    def serialize_iteration(self, result: IterationResult | None) -> BacktestIterationSummaryResponse | None:
        if result is None:
            return None
        return BacktestIterationSummaryResponse(
            range=self.range_payload(result.start_date, result.end_date),
            config=result.config.model_dump(),
            report=self.result_builder.report_snapshot(result.execution.report),
        )

    @staticmethod
    def range_payload(start_date: datetime | None, end_date: datetime | None) -> BacktestDateRangeResponse | None:
        if not start_date or not end_date:
            return None
        return BacktestDateRangeResponse(start=start_date.isoformat(), end=end_date.isoformat())

    @staticmethod
    def split_sample_range(start_date: datetime, end_date: datetime, in_sample_ratio: float):
        if in_sample_ratio >= 100:
            return None, None, None, None
        total_seconds = (end_date - start_date).total_seconds()
        if total_seconds <= 0:
            return None, None, None, None
        split_at = start_date + timedelta(seconds=total_seconds * (in_sample_ratio / 100.0))
        if split_at <= start_date or split_at >= end_date:
            return None, None, None, None
        return start_date, split_at, split_at, end_date

    @staticmethod
    def build_rolling_windows(
        start_date: datetime,
        end_date: datetime,
        window_count: int,
        in_sample_ratio: float,
    ) -> list[dict[str, Any]]:
        total_seconds = (end_date - start_date).total_seconds()
        if window_count <= 0 or total_seconds <= 0:
            return []
        step = total_seconds / window_count
        windows = []
        for index in range(window_count):
            window_start = start_date + timedelta(seconds=step * index)
            window_end = end_date if index == window_count - 1 else start_date + timedelta(seconds=step * (index + 1))
            if window_end <= window_start:
                continue
            if in_sample_ratio >= 100:
                windows.append({"train": None, "test": {"start": window_start, "end": window_end}})
                continue
            split_at = window_start + timedelta(
                seconds=(window_end - window_start).total_seconds() * (in_sample_ratio / 100.0)
            )
            if split_at <= window_start or split_at >= window_end:
                continue
            windows.append(
                {
                    "train": {"start": window_start, "end": split_at},
                    "test": {"start": split_at, "end": window_end},
                }
            )
        return windows
