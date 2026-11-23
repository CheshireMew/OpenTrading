"""Frozen execution entry point. Inputs are prices and an explicit numeric recipe.

This module, the simulator and history validation are saved together. Replays
use these files, not whichever validation/aggregation rules are installed later.
"""
from app.domain.local_backtest import simulate, validate_bars
from app.domain.backtest_history import validate_observed_bars, align_execution_bars


def prepare_history(rows, fine_rows, recipe):
    start, end, step, warmup = (recipe[k] for k in ('start_ms', 'end_ms', 'step_ms', 'warmup_bars'))
    if recipe['data_gap_policy'] == 'observed_bars':
        bars, gaps = validate_observed_bars(rows, start, end, step, warmup, end)
    else:
        bars, gaps = validate_bars(rows, start, end, step, warmup, end), []
    execution, alignment = None, None
    fine_step = recipe.get('execution_step_ms')
    if fine_step:
        if fine_rows is None:
            raise ValueError('缺少细周期行情快照')
        fine, _ = validate_observed_bars(fine_rows, start, end, fine_step, 0, end)
        execution, alignment = align_execution_bars(bars[warmup:], fine, step, fine_step)
        if alignment['fallback'] and recipe.get('execution_gap_policy', 'coarse_fallback') == 'reject':
            raise ValueError(f"细周期行情有 {alignment['fallback']} 个主周期区间缺失或不匹配，当前设置禁止回退")
    return bars, execution, gaps, alignment


def run(bars, execution, strategy, parameters, recipe, progress=None, record_factory=None):
    return simulate(bars, strategy, parameters, warmup=recipe['warmup_bars'],
        initial_cash=recipe['initial_cash'], position_pct=recipe['position_pct'],
        step_ms=recipe['step_ms'], execution_step_ms=recipe.get('execution_step_ms'),
        execution_bars=execution, intrabar_profit_protection=recipe['intrabar_profit_protection'],
        progress=progress, record_factory=record_factory)
