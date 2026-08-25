from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.domain.research import (
    ResearchDuplicateError,
    ResearchNotFoundError,
    ResearchRevisionConflictError,
)
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import (
    ResearchAlertRule,
    ResearchEvent,
    ResearchNote,
    ResearchWatchItem,
    ResearchWatchlist,
)
from utils.time import utc_now_naive


class ResearchRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def get_workbench(self, *, event_limit: int, note_limit: int) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            watchlists = list(
                session.scalars(
                    select(ResearchWatchlist).order_by(
                        ResearchWatchlist.archived_at.is_not(None),
                        ResearchWatchlist.position,
                        ResearchWatchlist.created_at,
                    )
                )
            )
            items = list(
                session.scalars(
                    select(ResearchWatchItem).order_by(
                        ResearchWatchItem.archived_at.is_not(None),
                        ResearchWatchItem.watchlist_id,
                        ResearchWatchItem.position,
                        ResearchWatchItem.created_at,
                    )
                )
            )
            notes = list(
                session.scalars(
                    select(ResearchNote)
                    .order_by(
                        ResearchNote.archived_at.is_not(None),
                        ResearchNote.occurred_at.desc(),
                        ResearchNote.created_at.desc(),
                    )
                    .limit(note_limit)
                )
            )
            alerts = list(
                session.scalars(
                    select(ResearchAlertRule).order_by(
                        ResearchAlertRule.archived_at.is_not(None),
                        ResearchAlertRule.enabled.desc(),
                        ResearchAlertRule.created_at.desc(),
                    )
                )
            )
            events = list(
                session.scalars(
                    select(ResearchEvent)
                    .order_by(ResearchEvent.occurred_at.desc(), ResearchEvent.created_at.desc())
                    .limit(event_limit)
                )
            )
            unacknowledged_count = int(
                session.scalar(
                    select(func.count()).select_from(ResearchEvent).where(ResearchEvent.acknowledged_at.is_(None))
                )
                or 0
            )
            return {
                "watchlists": [self._watchlist_payload(row) for row in watchlists],
                "items": [self._watch_item_payload(row) for row in items],
                "notes": [self._note_payload(row) for row in notes],
                "alerts": [self._alert_payload(row) for row in alerts],
                "events": [self._event_payload(row) for row in events],
                "unacknowledgedEventCount": unacknowledged_count,
            }

    def list_events(
        self,
        *,
        kind: str | None,
        unacknowledged_only: bool,
        since: datetime | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._database_runtime.session_scope() as session:
            filters = []
            if kind:
                filters.append(ResearchEvent.kind == kind)
            if unacknowledged_only:
                filters.append(ResearchEvent.acknowledged_at.is_(None))
            if since is not None:
                filters.append(ResearchEvent.occurred_at >= since)
            query = select(ResearchEvent).where(*filters)
            rows = list(
                session.scalars(
                    query.order_by(ResearchEvent.occurred_at.desc(), ResearchEvent.created_at.desc()).limit(limit)
                )
            )
            total = int(
                session.scalar(select(func.count()).select_from(ResearchEvent).where(*filters)) or 0
            )
            return [self._event_payload(row) for row in rows], total

    def create_watchlist(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
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
            self._add_event(
                session,
                entity_type="watchlist",
                entity_id=row.id,
                kind="watchlist_created",
                title=f"创建研究列表：{row.name}",
                occurred_at=now,
            )
            session.flush()
            return self._watchlist_payload(row)

    def update_watchlist(self, watchlist_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require_row(session, ResearchWatchlist, watchlist_id, expected_version)
            row.name = payload["name"]
            row.description = payload.get("description", "")
            self._touch(row)
            self._add_event(
                session,
                entity_type="watchlist",
                entity_id=row.id,
                kind="watchlist_updated",
                title=f"更新研究列表：{row.name}",
            )
            session.flush()
            return self._watchlist_payload(row)

    def set_watchlist_archived(self, watchlist_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require_row(session, ResearchWatchlist, watchlist_id, expected_version)
            row.archived_at = utc_now_naive() if archived else None
            self._touch(row)
            self._add_event(
                session,
                entity_type="watchlist",
                entity_id=row.id,
                kind="watchlist_archived" if archived else "watchlist_restored",
                title=f"{'归档' if archived else '恢复'}研究列表：{row.name}",
            )
            session.flush()
            return self._watchlist_payload(row)

    def create_watch_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
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
                id=uuid4().hex,
                position=position,
                version=1,
                created_at=now,
                updated_at=now,
                **payload,
            )
            session.add(row)
            self._add_event(
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
            return self._watch_item_payload(row)

    def update_watch_item(self, item_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require_row(session, ResearchWatchItem, item_id, expected_version)
            target_list = session.get(ResearchWatchlist, payload["watchlist_id"])
            if target_list is None or target_list.archived_at is not None:
                raise ResearchNotFoundError("研究列表不存在或已归档")
            for key, value in payload.items():
                setattr(row, key, value)
            self._touch(row)
            self._add_event(
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
            return self._watch_item_payload(row)

    def set_watch_item_archived(self, item_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return self._set_archived(
            ResearchWatchItem,
            item_id,
            expected_version,
            archived,
            entity_type="watch_item",
            title=lambda row: f"{'归档' if archived else '恢复'}研究标的：{row.symbol}",
            symbol=lambda row: row.symbol,
        )

    def create_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            self._validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
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
            self._add_event(
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
            return self._note_payload(row)

    def update_note(self, note_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require_row(session, ResearchNote, note_id, expected_version)
            self._validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
            for key, value in payload.items():
                if value is not None or key not in {"occurred_at", "watch_item_id"}:
                    setattr(row, key, value)
            self._touch(row)
            self._add_event(
                session,
                entity_type="note",
                entity_id=row.id,
                symbol=row.symbol,
                kind="note_updated",
                title=f"更新笔记：{row.title}",
                body=row.content,
            )
            session.flush()
            return self._note_payload(row)

    def set_note_archived(self, note_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return self._set_archived(
            ResearchNote,
            note_id,
            expected_version,
            archived,
            entity_type="note",
            title=lambda row: f"{'归档' if archived else '恢复'}研究笔记：{row.title}",
            symbol=lambda row: row.symbol,
        )

    def create_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            self._validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
            now = utc_now_naive()
            row = ResearchAlertRule(
                id=uuid4().hex,
                version=1,
                created_at=now,
                updated_at=now,
                **payload,
            )
            session.add(row)
            self._add_event(
                session,
                entity_type="alert",
                entity_id=row.id,
                symbol=row.symbol,
                kind="alert_created",
                title=f"创建提醒：{row.name}",
                payload={"metric": row.metric, "operator": row.operator, "threshold": row.threshold},
                occurred_at=now,
            )
            session.flush()
            return self._alert_payload(row)

    def update_alert(self, alert_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require_row(session, ResearchAlertRule, alert_id, expected_version)
            self._validate_watch_item_link(session, payload.get("watch_item_id"), payload["symbol"])
            for key, value in payload.items():
                setattr(row, key, value)
            self._touch(row)
            self._add_event(
                session,
                entity_type="alert",
                entity_id=row.id,
                symbol=row.symbol,
                kind="alert_updated",
                title=f"更新提醒：{row.name}",
            )
            session.flush()
            return self._alert_payload(row)

    def set_alert_archived(self, alert_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return self._set_archived(
            ResearchAlertRule,
            alert_id,
            expected_version,
            archived,
            entity_type="alert",
            title=lambda row: f"{'归档' if archived else '恢复'}提醒：{row.name}",
            symbol=lambda row: row.symbol,
        )

    def acknowledge_event(self, event_id: str, acknowledged: bool) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = session.get(ResearchEvent, event_id)
            if row is None:
                raise ResearchNotFoundError("研究事件不存在")
            row.acknowledged_at = utc_now_naive() if acknowledged else None
            session.flush()
            return self._event_payload(row)

    def list_enabled_alerts(self) -> list[dict[str, Any]]:
        with self._database_runtime.session_scope() as session:
            rows = list(
                session.scalars(
                    select(ResearchAlertRule)
                    .where(
                        ResearchAlertRule.archived_at.is_(None),
                        ResearchAlertRule.enabled == 1,
                    )
                    .order_by(ResearchAlertRule.symbol, ResearchAlertRule.created_at)
                )
            )
            return [self._alert_runtime_payload(row) for row in rows]

    def record_alert_evaluation(
        self,
        alert_id: str,
        *,
        value: float,
        evaluated_at: datetime,
        triggered: bool,
    ) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = session.get(ResearchAlertRule, alert_id)
            if row is None or row.archived_at is not None:
                raise ResearchNotFoundError("提醒规则不存在或已归档")
            row.last_value = value
            row.last_evaluated_at = evaluated_at
            if triggered:
                row.last_triggered_at = evaluated_at
                self._add_event(
                    session,
                    entity_type="alert",
                    entity_id=row.id,
                    symbol=row.symbol,
                    kind="alert_triggered",
                    title=f"提醒触发：{row.name}",
                    body=f"{row.symbol} 的 {row.metric} 当前值为 {value:g}",
                    payload={
                        "metric": row.metric,
                        "operator": row.operator,
                        "threshold": row.threshold,
                        "secondaryThreshold": row.secondary_threshold,
                        "value": value,
                        "notificationChannels": list(row.notification_channels or []),
                    },
                    occurred_at=evaluated_at,
                )
            session.flush()
            return self._alert_payload(row)

    def _set_archived(
        self,
        model,
        record_id: str,
        expected_version: int,
        archived: bool,
        *,
        entity_type: str,
        title,
        symbol,
    ) -> dict[str, Any]:
        with self._database_runtime.session_scope() as session:
            row = self._require_row(session, model, record_id, expected_version)
            row.archived_at = utc_now_naive() if archived else None
            self._touch(row)
            self._add_event(
                session,
                entity_type=entity_type,
                entity_id=row.id,
                symbol=symbol(row),
                kind=f"{entity_type}_{'archived' if archived else 'restored'}",
                title=title(row),
            )
            session.flush()
            if model is ResearchWatchItem:
                return self._watch_item_payload(row)
            if model is ResearchNote:
                return self._note_payload(row)
            return self._alert_payload(row)

    @staticmethod
    def _require_row(session, model, record_id: str, expected_version: int):
        row = session.get(model, record_id)
        if row is None:
            raise ResearchNotFoundError("研究记录不存在")
        if row.version != expected_version:
            raise ResearchRevisionConflictError("研究记录已在其它窗口更新，请重新载入后再试")
        return row

    @staticmethod
    def _validate_watch_item_link(session, item_id: str | None, symbol: str) -> None:
        if not item_id:
            return
        item = session.get(ResearchWatchItem, item_id)
        if item is None:
            raise ResearchNotFoundError("关联的研究标的不存在")
        if item.symbol != symbol:
            raise ResearchRevisionConflictError("笔记或提醒的标的与研究标的不一致")

    @staticmethod
    def _touch(row) -> None:
        row.version += 1
        row.updated_at = utc_now_naive()

    @staticmethod
    def _add_event(
        session,
        *,
        entity_type: str,
        entity_id: str | None,
        kind: str,
        title: str,
        symbol: str | None = None,
        body: str = "",
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        now = utc_now_naive()
        session.add(
            ResearchEvent(
                id=uuid4().hex,
                entity_type=entity_type,
                entity_id=entity_id,
                symbol=symbol,
                kind=kind,
                title=title,
                body=body,
                payload=payload or {},
                occurred_at=occurred_at or now,
                created_at=now,
            )
        )

    @staticmethod
    def _watchlist_payload(row: ResearchWatchlist) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "position": row.position,
            "version": row.version,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    @staticmethod
    def _watch_item_payload(row: ResearchWatchItem) -> dict[str, Any]:
        return {
            "id": row.id,
            "watchlistId": row.watchlist_id,
            "symbol": row.symbol,
            "assetClass": row.asset_class,
            "displayName": row.display_name,
            "thesis": row.thesis,
            "targetPrice": row.target_price,
            "invalidationPrice": row.invalidation_price,
            "tags": list(row.tags or []),
            "sourceContext": dict(row.source_context or {}),
            "position": row.position,
            "version": row.version,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    @staticmethod
    def _note_payload(row: ResearchNote) -> dict[str, Any]:
        return {
            "id": row.id,
            "watchItemId": row.watch_item_id,
            "symbol": row.symbol,
            "kind": row.kind,
            "title": row.title,
            "content": row.content,
            "snapshot": dict(row.snapshot or {}),
            "version": row.version,
            "occurredAt": row.occurred_at,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    @staticmethod
    def _alert_payload(row: ResearchAlertRule) -> dict[str, Any]:
        return {
            "id": row.id,
            "watchItemId": row.watch_item_id,
            "symbol": row.symbol,
            "name": row.name,
            "metric": row.metric,
            "operator": row.operator,
            "threshold": row.threshold,
            "secondaryThreshold": row.secondary_threshold,
            "enabled": bool(row.enabled),
            "cooldownMinutes": row.cooldown_minutes,
            "notificationChannels": list(row.notification_channels or []),
            "configuration": dict(row.configuration or {}),
            "lastValue": row.last_value,
            "lastEvaluatedAt": row.last_evaluated_at,
            "lastTriggeredAt": row.last_triggered_at,
            "version": row.version,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    @classmethod
    def _alert_runtime_payload(cls, row: ResearchAlertRule) -> dict[str, Any]:
        payload = cls._alert_payload(row)
        payload.update(
            {
                "watch_item_id": row.watch_item_id,
                "secondary_threshold": row.secondary_threshold,
                "cooldown_minutes": row.cooldown_minutes,
                "notification_channels": list(row.notification_channels or []),
                "last_value": row.last_value,
                "last_evaluated_at": row.last_evaluated_at,
                "last_triggered_at": row.last_triggered_at,
            }
        )
        return payload

    @staticmethod
    def _event_payload(row: ResearchEvent) -> dict[str, Any]:
        return {
            "id": row.id,
            "entityType": row.entity_type,
            "entityId": row.entity_id,
            "symbol": row.symbol,
            "kind": row.kind,
            "title": row.title,
            "body": row.body,
            "payload": dict(row.payload or {}),
            "occurredAt": row.occurred_at,
            "acknowledgedAt": row.acknowledged_at,
            "createdAt": row.created_at,
        }
