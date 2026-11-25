from __future__ import annotations

from typing import Any

from uuid import uuid4

from sqlalchemy import delete, func, select

from sqlalchemy.exc import IntegrityError

from app.domain.research import ResearchDuplicateError, ResearchNotFoundError, ResearchRevisionConflictError

from app.infra.db.database import DatabaseRuntime

from app.infra.persistence.write_session import write_session

from app.infra.db.schema import ResearchAlertRule, ResearchEvent, ResearchNote, ResearchWatchItem, ResearchWatchlist

from utils.time import utc_now_naive

from app.infra.persistence.research_rows import (
    set_archived,
    require_row,
    validate_watch_item_link,
    touch,
    add_event,
    watchlist_payload,
    watch_item_payload,
    note_payload,
)


class ResearchRecordRepository:
    def delete_record(self, kind: str, record_id: str, expected_version: int) -> None:
        model = {"watchlist": ResearchWatchlist, "item": ResearchWatchItem, "note": ResearchNote}[kind]
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = require_row(session, model, record_id, expected_version)
            deleted_ids = {record_id}
            if kind in {"watchlist", "item"}:
                item_ids = list(session.scalars(select(ResearchWatchItem.id).where(
                    ResearchWatchItem.watchlist_id == record_id if kind == "watchlist" else ResearchWatchItem.id == record_id)))
                deleted_ids.update(item_ids)
                for child in (ResearchNote, ResearchAlertRule):
                    deleted_ids.update(session.scalars(select(child.id).where(child.watch_item_id.in_(item_ids))))
                    session.execute(delete(child).where(child.watch_item_id.in_(item_ids)))
                if kind == "watchlist":
                    session.execute(delete(ResearchWatchItem).where(ResearchWatchItem.id.in_(item_ids)))
            session.execute(delete(ResearchEvent).where(ResearchEvent.entity_id.in_(deleted_ids)))
            session.delete(row)

    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def create_watchlist(self, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            now = utc_now_naive()
            position = int(session.scalar(select(func.max(ResearchWatchlist.position))) or -1) + 1
            row = ResearchWatchlist(
                id=uuid4().hex,
                name=payload["name"],
                description=payload.get("description", ""),
                position=position,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            add_event(
                session,
                entity_type="watchlist",
                entity_id=row.id,
                kind="watchlist_created",
                title=f"创建研究列表：{row.name}",
                occurred_at=now,
            )
            session.flush()
            return watchlist_payload(row)

    def update_watchlist(self, watchlist_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = require_row(session, ResearchWatchlist, watchlist_id, expected_version)
            row.name = payload["name"]
            row.description = payload.get("description", "")
            touch(row)
            add_event(
                session,
                entity_type="watchlist",
                entity_id=row.id,
                kind="watchlist_updated",
                title=f"更新研究列表：{row.name}",
            )
            session.flush()
            return watchlist_payload(row)

    def set_watchlist_archived(self, watchlist_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = require_row(session, ResearchWatchlist, watchlist_id, expected_version)
            row.archived_at = utc_now_naive() if archived else None
            touch(row)
            add_event(
                session,
                entity_type="watchlist",
                entity_id=row.id,
                kind="watchlist_archived" if archived else "watchlist_restored",
                title=f"{('归档' if archived else '恢复')}研究列表：{row.name}",
            )
            session.flush()
            return watchlist_payload(row)

    def create_watch_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            watchlist = session.get(ResearchWatchlist, payload["watchlist_id"])
            if watchlist is None or watchlist.archived_at is not None:
                raise ResearchNotFoundError("研究列表不存在或已归档")
            position = (
                int(
                    session.scalar(
                        select(func.max(ResearchWatchItem.position)).where(
                            ResearchWatchItem.watchlist_id == watchlist.id
                        )
                    )
                    or -1
                )
                + 1
            )
            now = utc_now_naive()
            row = ResearchWatchItem(
                id=uuid4().hex, position=position, version=1, created_at=now, updated_at=now, **payload
            )
            session.add(row)
            add_event(
                session,
                entity_type="watch_item",
                entity_id=row.id,
                symbol=row.symbol,
                kind="watch_item_created",
                title=f"加入研究列表：{row.symbol}",
                body=row.thesis,
                payload={"watchlistId": row.watchlist_id, "tags": row.tags},
                occurred_at=now,
            )
            try:
                session.flush()
            except IntegrityError as exc:
                raise ResearchDuplicateError("这个标的已经在该研究列表中") from exc
            return watch_item_payload(row)

    def update_watch_item(self, item_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = require_row(session, ResearchWatchItem, item_id, expected_version)
            target_list = session.get(ResearchWatchlist, payload["watchlist_id"])
            if target_list is None or target_list.archived_at is not None:
                raise ResearchNotFoundError("研究列表不存在或已归档")
            for key, value in payload.items():
                setattr(row, key, value)
            touch(row)
            add_event(
                session,
                entity_type="watch_item",
                entity_id=row.id,
                symbol=row.symbol,
                kind="watch_item_updated",
                title=f"更新研究判断：{row.symbol}",
                body=row.thesis,
            )
            try:
                session.flush()
            except IntegrityError as exc:
                raise ResearchDuplicateError("这个标的已经在该研究列表中") from exc
            return watch_item_payload(row)

    def set_watch_item_archived(self, item_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return set_archived(
            self._database_runtime,
            ResearchWatchItem,
            item_id,
            expected_version,
            archived,
            entity_type="watch_item",
            title=lambda row: f"{('归档' if archived else '恢复')}研究标的：{row.symbol}",
            symbol=lambda row: row.symbol,
        )

    def create_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
            now = utc_now_naive()
            row = ResearchNote(
                id=uuid4().hex,
                version=1,
                occurred_at=payload.pop("occurred_at", None) or now,
                created_at=now,
                updated_at=now,
                **payload,
            )
            session.add(row)
            add_event(
                session,
                entity_type="note",
                entity_id=row.id,
                symbol=row.symbol,
                kind="note_created",
                title=row.title,
                body=row.content,
                payload={"noteKind": row.kind, "snapshot": row.snapshot},
                occurred_at=row.occurred_at,
            )
            session.flush()
            return note_payload(row)

    def update_note(self, note_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = require_row(session, ResearchNote, note_id, expected_version)
            validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
            for key, value in payload.items():
                if value is not None or key not in {"occurred_at", "watch_item_id"}:
                    setattr(row, key, value)
            touch(row)
            add_event(
                session,
                entity_type="note",
                entity_id=row.id,
                symbol=row.symbol,
                kind="note_updated",
                title=f"更新笔记：{row.title}",
                body=row.content,
            )
            session.flush()
            return note_payload(row)

    def set_note_archived(self, note_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return set_archived(
            self._database_runtime,
            ResearchNote,
            note_id,
            expected_version,
            archived,
            entity_type="note",
            title=lambda row: f"{('归档' if archived else '恢复')}研究笔记：{row.title}",
            symbol=lambda row: row.symbol,
        )
