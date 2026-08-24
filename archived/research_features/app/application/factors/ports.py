from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.domain.factors.signal_execution_core import FactorSignalPosition


class FactorResearchProvider(Protocol):
    def get_run(self, run_id: int) -> Any | None:
        ...

    def build_stored_blend_frame(self, run_id: int) -> tuple[Any, Any]:
        ...

    def build_live_blend_frame(self, run_id: int, end_date: datetime | None = None) -> tuple[Any, Any]:
        ...


class FactorSignalCore(Protocol):
    def create_state(self, initial_cash: float, **kwargs: Any) -> Any:
        ...

    def run_batch(self, **kwargs: Any) -> Any:
        ...

    def serialize_position(self, position: FactorSignalPosition | None, *, symbol: str) -> dict[str, Any] | None:
        ...

    def deserialize_position(self, payload: dict[str, Any] | None) -> FactorSignalPosition | None:
        ...


class FactorPaperPersistence(Protocol):
    def persist_increment(self, **kwargs: Any) -> None:
        ...
