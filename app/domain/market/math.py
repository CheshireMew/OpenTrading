from __future__ import annotations


def percentage_change(
    current: float | None,
    previous: float | None,
    *,
    absolute_baseline: bool = False,
) -> float | None:
    if current is None or previous in (None, 0):
        return None
    baseline = abs(previous) if absolute_baseline else previous
    return ((current - previous) / baseline) * 100.0
