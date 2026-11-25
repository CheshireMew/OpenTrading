from __future__ import annotations

from datetime import datetime

from typing import Any

from sqlalchemy import func, select, tuple_

from app.domain.research import ResearchNotFoundError, ResearchRevisionConflictError

from app.infra.db.database import DatabaseRuntime

from app.infra.persistence.write_session import write_session

from app.infra.db.schema import ResearchAlertRule, ResearchEvent, ResearchNote, ResearchWatchItem, ResearchWatchlist

from utils.time import utc_now_naive

from app.infra.persistence.research_rows import (
    watchlist_payload,
    watch_item_payload,
    note_payload,
    alert_payload,
    event_payload,
)


class ResearchWorkbenchRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def list_notes(self, symbol: str, *, offset: int = 0, limit: int = 200) -> tuple[list[dict[str, Any]], int]:
        with self._database_runtime.session_scope() as session:
            matching = func.lower(ResearchNote.symbol) == symbol.casefold()
            total = int(session.scalar(select(func.count()).select_from(ResearchNote).where(matching)) or 0)
            rows = session.scalars(select(ResearchNote).where(matching).order_by(
                ResearchNote.archived_at.is_not(None), ResearchNote.occurred_at.desc(),
                ResearchNote.created_at.desc(), ResearchNote.id.desc(),
            ).offset(offset).limit(limit))
            return [note_payload(row) for row in rows], total

    def get_asset_records(self, symbol: str) -> dict[str, Any]:
        # Filter in SQL before imposing a page limit. Other assets cannot evict
        # this asset's older notes or events from its research page.
        with self._database_runtime.session_scope() as session:
            items = session.scalars(select(ResearchWatchItem).where(func.lower(ResearchWatchItem.symbol) == symbol.casefold()))
            alerts = session.scalars(select(ResearchAlertRule).where(func.lower(ResearchAlertRule.symbol) == symbol.casefold()))
            events = session.scalars(select(ResearchEvent).where(func.lower(ResearchEvent.symbol) == symbol.casefold())
                                     .order_by(ResearchEvent.occurred_at.desc(), ResearchEvent.id.desc()).limit(500))
            result = {"items": [watch_item_payload(row) for row in items],
                      "alerts": [alert_payload(row) for row in alerts],
                      "events": [event_payload(row) for row in events]}
        notes, total = self.list_notes(symbol, limit=200)
        return {**result, "notes": notes, "notesTotal": total}

    def get_workbench(self, *, event_limit: int, note_limit: int) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
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
            # Retire rules left behind by older versions. Notifications are separate
            # events; an expired one-shot rule has no remaining job to perform.
            remaining = []
            for row in alerts:
                once = row.configuration.get("once", bool(row.configuration.get("chartSymbolId")))
                if row.archived_at or (once and not row.enabled and row.last_triggered_at):
                    session.delete(row)
                else:
                    remaining.append(row)
            alerts = remaining
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
                "watchlists": [watchlist_payload(row) for row in watchlists],
                "items": [watch_item_payload(row) for row in items],
                "notes": [note_payload(row) for row in notes],
                "alerts": [alert_payload(row) for row in alerts],
                "events": [event_payload(row) for row in events],
                "unacknowledgedEventCount": unacknowledged_count,
            }

    def list_events(
        self, *, kind: str | None, unacknowledged_only: bool, since: datetime | None, limit: int,
        before: tuple[datetime, datetime, str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            filters = []
            if kind:
                filters.append(ResearchEvent.kind == kind)
            if unacknowledged_only:
                filters.append(ResearchEvent.acknowledged_at.is_(None))
            if since is not None:
                filters.append(ResearchEvent.occurred_at >= since)
            query = select(ResearchEvent).where(*filters)
            if before is not None:
                query = query.where(tuple_(ResearchEvent.occurred_at, ResearchEvent.created_at, ResearchEvent.id) < before)
            rows = list(
                session.scalars(
                    query.order_by(ResearchEvent.occurred_at.desc(), ResearchEvent.created_at.desc(), ResearchEvent.id.desc()).limit(limit)
                )
            )
            total = int(session.scalar(select(func.count()).select_from(ResearchEvent).where(*filters)) or 0)
            return ([event_payload(row) for row in rows], total)

    def acknowledge_event(self, event_id: str, acknowledged: bool) -> dict[str, Any]:
        with write_session(self._database_runtime, ResearchRevisionConflictError) as session:
            row = session.get(ResearchEvent, event_id)
            if row is None:
                raise ResearchNotFoundError("研究事件不存在")
            row.acknowledged_at = utc_now_naive() if acknowledged else None
            session.flush()
            return event_payload(row)
