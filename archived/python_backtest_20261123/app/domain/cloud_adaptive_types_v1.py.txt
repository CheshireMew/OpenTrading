"""Opt-in, close-known adaptive protection instructions for research replays."""
from dataclasses import dataclass
from app.domain.local_backtest import Intent, BarResult


@dataclass(frozen=True)
class AdaptiveIntent(Intent):
    activation_distance: float | None = None


@dataclass(frozen=True)
class AdaptiveResult(BarResult):
    trailing_distance: float | None = None
    record_observation: bool = False
