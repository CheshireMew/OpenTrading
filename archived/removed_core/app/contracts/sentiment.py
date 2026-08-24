from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class SentimentRecord:
    date: datetime
    value: int
    classification: str
    timestamp: int
