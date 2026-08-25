from __future__ import annotations

from typing import Any, Protocol


class DataHealthRepositoryPort(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
