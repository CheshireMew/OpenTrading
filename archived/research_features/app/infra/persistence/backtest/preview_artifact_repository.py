from __future__ import annotations

from app.application.backtest.preview_artifact_store import StoredStrategyPreview
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import BacktestPreviewArtifact


class BacktestPreviewArtifactRepository:
    def __init__(self, *, database_runtime: DatabaseRuntime) -> None:
        self.database_runtime = database_runtime

    def save(self, preview: StoredStrategyPreview) -> None:
        with self.database_runtime.session_scope() as session:
            session.merge(
                BacktestPreviewArtifact(
                    preview_id=preview.preview_id,
                    fingerprint=preview.fingerprint,
                    command_payload=preview.command_payload,
                    artifact=preview.artifact,
                )
            )
            session.flush()

    def get(self, preview_id: str) -> StoredStrategyPreview | None:
        with self.database_runtime.session_scope() as session:
            record = session.get(BacktestPreviewArtifact, preview_id)
            if record is None:
                return None
            return StoredStrategyPreview(
                preview_id=record.preview_id,
                fingerprint=record.fingerprint,
                command_payload=dict(record.command_payload or {}),
                artifact=dict(record.artifact or {}),
            )
