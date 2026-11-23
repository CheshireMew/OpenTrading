"""Price/metric conditions shared by evaluation and atomic persistence."""
from datetime import datetime, timedelta
from typing import Any


def should_trigger(rule: dict[str, Any], value: float, evaluated_at: datetime) -> bool:
    operator, threshold = rule["operator"], float(rule["threshold"])
    secondary, prior = rule.get("secondary_threshold"), rule.get("last_value")
    above = prior is not None and float(prior) < threshold <= value
    below = prior is not None and float(prior) > threshold >= value
    conditions = {
        "gt": value > threshold, "gte": value >= threshold,
        "lt": value < threshold, "lte": value <= threshold,
        "crosses": above or below, "crosses_above": above, "crosses_below": below,
        "between": secondary is not None and threshold <= value <= float(secondary),
        "outside": secondary is not None and (value < threshold or value > float(secondary)),
    }
    if not conditions.get(operator, False):
        return False
    last = rule.get("last_triggered_at")
    return last is None or evaluated_at >= last + timedelta(minutes=max(int(rule.get("cooldown_minutes") or 0), 0))
