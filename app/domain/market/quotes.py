"""A quote never loses its observation time when it crosses a layer."""
from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class MarketQuote:
    value: float | None = None
    observed_at: int | None = None
    received_at: int | None = None
    source: str = "unavailable"
    market: str = "spot"

    def fresh(self, now_ms: int, max_age_seconds: float) -> bool:
        return bool(self.value is not None and math.isfinite(self.value) and self.value > 0
                    and self.observed_at is not None
                    and -5_000 <= now_ms - self.observed_at <= max_age_seconds * 1000)
