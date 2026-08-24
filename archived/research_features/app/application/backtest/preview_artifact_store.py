from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class StoredStrategyPreview:
    preview_id: str
    fingerprint: str
    command_payload: dict[str, Any]
    artifact: dict[str, Any]


class StrategyPreviewArtifactStore(Protocol):
    def save(self, preview: StoredStrategyPreview) -> None: ...

    def get(self, preview_id: str) -> StoredStrategyPreview | None: ...
