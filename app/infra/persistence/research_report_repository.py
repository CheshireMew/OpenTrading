from __future__ import annotations
from typing import Any
from uuid import uuid4
from sqlalchemy import func, select
from app.domain.research import ResearchNotFoundError, ResearchRevisionConflictError
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import ResearchEvent, ResearchReportRecord
from utils.time import utc_now_naive


class ResearchReportRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def create_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            now = utc_now_naive()
            row = ResearchReportRecord(id=uuid4().hex, version=1, created_at=now, updated_at=now, **payload)
            session.add(row)
            session.add(
                ResearchEvent(
                    id=uuid4().hex,
                    entity_type="research_report",
                    entity_id=row.id,
                    symbol=row.symbol,
                    kind="report_generated",
                    title=f"生成研究报告：{row.title}",
                    body="",
                    payload={"reportType": row.report_type, "portfolioId": row.portfolio_id},
                    occurred_at=now,
                    created_at=now,
                )
            )
            session.flush()
            return self._payload(row)

    def get_report(self, report_id: str) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            return self._payload(self._require(session, report_id))

    def list_reports(self, *, include_archived: bool, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        with self._database_runtime.session_scope() as session:
            filters = [] if include_archived else [ResearchReportRecord.archived_at.is_(None)]
            total = int(session.scalar(select(func.count()).select_from(ResearchReportRecord).where(*filters)) or 0)
            rows = list(
                session.scalars(
                    select(ResearchReportRecord)
                    .where(*filters)
                    .order_by(ResearchReportRecord.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            return [self._payload(row) for row in rows], total

    def set_report_archived(self, report_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require(session, report_id)
            if row.version != expected_version:
                raise ResearchRevisionConflictError("研究报告已在其它窗口更新，请重新载入")
            row.archived_at = utc_now_naive() if archived else None
            row.version += 1
            row.updated_at = utc_now_naive()
            session.flush()
            return self._payload(row)

    @staticmethod
    def _require(session, report_id):
        row = session.get(ResearchReportRecord, report_id)
        if row is None:
            raise ResearchNotFoundError("研究报告不存在")
        return row

    @staticmethod
    def _payload(row):
        return {
            "id": row.id,
            "title": row.title,
            "reportType": row.report_type,
            "symbol": row.symbol,
            "portfolioId": row.portfolio_id,
            "contentMarkdown": row.content_markdown,
            "dataSnapshot": dict(row.data_snapshot or {}),
            "version": row.version,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }
