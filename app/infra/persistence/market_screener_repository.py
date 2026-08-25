from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from app.domain.research import ResearchNotFoundError, ResearchRevisionConflictError
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import MarketScreenerRun, ResearchEvent, SavedMarketScreener
from utils.time import utc_now_naive


class MarketScreenerRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def list_screeners(self, *, include_archived: bool) -> list[dict[str, Any]]:
        with self._database_runtime.session_scope() as session:
            statement = select(SavedMarketScreener)
            if not include_archived:
                statement = statement.where(SavedMarketScreener.archived_at.is_(None))
            rows = list(
                session.scalars(
                    statement.order_by(
                        SavedMarketScreener.archived_at.is_not(None), SavedMarketScreener.updated_at.desc()
                    )
                )
            )
            return [self._screener_payload(row) for row in rows]

    def create_screener(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            now = utc_now_naive()
            row = SavedMarketScreener(id=uuid4().hex, version=1, created_at=now, updated_at=now, **payload)
            session.add(row)
            self._event(session, row, "screener_created", f"创建市场筛选器：{row.name}")
            session.flush()
            return self._screener_payload(row)

    def update_screener(self, screener_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require(session, screener_id, expected_version)
            row.name, row.description, row.filters = payload["name"], payload["description"], payload["filters"]
            row.version += 1
            row.updated_at = utc_now_naive()
            self._event(session, row, "screener_updated", f"更新市场筛选器：{row.name}")
            session.flush()
            return self._screener_payload(row)

    def set_screener_archived(self, screener_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require(session, screener_id, expected_version)
            row.archived_at = utc_now_naive() if archived else None
            row.version += 1
            row.updated_at = utc_now_naive()
            self._event(
                session,
                row,
                "screener_archived" if archived else "screener_restored",
                f"{'归档' if archived else '恢复'}市场筛选器：{row.name}",
            )
            session.flush()
            return self._screener_payload(row)

    def get_screener(self, screener_id: str) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            return self._screener_payload(self._require(session, screener_id))

    def save_run(self, screener_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            screener = self._require(session, screener_id)
            now = utc_now_naive()
            row = MarketScreenerRun(id=uuid4().hex, screener_id=screener_id, created_at=now, **payload)
            session.add(row)
            self._event(
                session,
                screener,
                "screener_run",
                f"运行市场筛选器：{screener.name}",
                payload={"runId": row.id, "resultCount": row.result_count},
            )
            session.flush()
            return self._run_payload(row)

    def get_run_as_of(self, screener_id: str, as_of: datetime) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            self._require(session, screener_id)
            row = session.scalar(
                select(MarketScreenerRun)
                .where(MarketScreenerRun.screener_id == screener_id, MarketScreenerRun.snapshot_as_of <= as_of)
                .order_by(MarketScreenerRun.snapshot_as_of.desc())
                .limit(1)
            )
            if row is None:
                raise ResearchNotFoundError("所选时间之前没有保存过筛选结果")
            payload = self._run_payload(row)
            payload["historicalReplay"] = True
            return payload

    def list_runs(self, screener_id: str, *, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        with self._database_runtime.session_scope() as session:
            self._require(session, screener_id)
            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(MarketScreenerRun)
                    .where(MarketScreenerRun.screener_id == screener_id)
                )
                or 0
            )
            rows = list(
                session.scalars(
                    select(MarketScreenerRun)
                    .where(MarketScreenerRun.screener_id == screener_id)
                    .order_by(MarketScreenerRun.snapshot_as_of.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            return [self._run_payload(row) for row in rows], total

    @staticmethod
    def _require(session, screener_id: str, expected_version: int | None = None) -> SavedMarketScreener:
        row = session.get(SavedMarketScreener, screener_id)
        if row is None:
            raise ResearchNotFoundError("市场筛选器不存在")
        if expected_version is not None and row.version != expected_version:
            raise ResearchRevisionConflictError("市场筛选器已在其它窗口更新，请重新载入")
        return row

    @staticmethod
    def _event(session, row, kind: str, title: str, payload: dict[str, Any] | None = None):
        now = utc_now_naive()
        session.add(
            ResearchEvent(
                id=uuid4().hex,
                entity_type="market_screener",
                entity_id=row.id,
                symbol=None,
                kind=kind,
                title=title,
                body="",
                payload=payload or {},
                occurred_at=now,
                created_at=now,
            )
        )

    @staticmethod
    def _screener_payload(row: SavedMarketScreener) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "filters": dict(row.filters or {}),
            "version": row.version,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    @staticmethod
    def _run_payload(row: MarketScreenerRun) -> dict[str, Any]:
        return {
            "id": row.id,
            "screenerId": row.screener_id,
            "filters": dict(row.filters_snapshot or {}),
            "resultItems": list(row.result_items or []),
            "resultCount": row.result_count,
            "snapshotAsOf": row.snapshot_as_of,
            "evaluatedAt": row.evaluated_at,
            "historicalReplay": False,
        }
