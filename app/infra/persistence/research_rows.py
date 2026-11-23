from __future__ import annotations

from datetime import datetime

from typing import Any

from uuid import uuid4

from app.domain.research import ResearchNotFoundError, ResearchRevisionConflictError

from app.infra.persistence.write_session import write_session

from app.infra.db.schema import ResearchAlertRule, ResearchEvent, ResearchNote, ResearchWatchItem, ResearchWatchlist

from utils.time import utc_now_naive


def set_archived(
    database_runtime, model, record_id: str, expected_version: int, archived: bool, *, entity_type: str, title, symbol
) -> dict[str, Any]:
    with write_session(database_runtime, ResearchRevisionConflictError) as session:
        row = require_row(session, model, record_id, expected_version)
        row.archived_at = utc_now_naive() if archived else None
        touch(row)
        add_event(
            session,
            entity_type=entity_type,
            entity_id=row.id,
            symbol=symbol(row),
            kind=f"{entity_type}_{('archived' if archived else 'restored')}",
            title=title(row),
        )
        session.flush()
        if model is ResearchWatchItem:
            return watch_item_payload(row)
        if model is ResearchNote:
            return note_payload(row)
        return alert_payload(row)


def require_row(session, model, record_id: str, expected_version: int):
    row = session.get(model, record_id)
    if row is None:
        raise ResearchNotFoundError("研究记录不存在")
    if row.version != expected_version:
        raise ResearchRevisionConflictError("研究记录已在其它窗口更新，请重新载入后再试")
    return row


def validate_watch_item_link(session, item_id: str | None, symbol: str) -> None:
    if not item_id:
        return
    item = session.get(ResearchWatchItem, item_id)
    if item is None:
        raise ResearchNotFoundError("关联的研究标的不存在")
    if item.symbol != symbol:
        raise ResearchRevisionConflictError("笔记或提醒的标的与研究标的不一致")


def touch(row) -> None:
    row.version += 1
    row.updated_at = utc_now_naive()


def add_event(
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


def watchlist_payload(row: ResearchWatchlist) -> dict[str, Any]:
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


def watch_item_payload(row: ResearchWatchItem) -> dict[str, Any]:
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


def note_payload(row: ResearchNote) -> dict[str, Any]:
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


def alert_payload(row: ResearchAlertRule) -> dict[str, Any]:
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


def alert_runtime_payload(row: ResearchAlertRule) -> dict[str, Any]:
    payload = alert_payload(row)
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


def event_payload(row: ResearchEvent) -> dict[str, Any]:
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
