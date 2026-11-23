from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexFetchResult:
    data: list[list[float]]
    source: str
    is_close_only: bool = False
