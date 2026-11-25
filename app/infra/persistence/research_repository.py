from __future__ import annotations

from datetime import datetime

from typing import Any

from app.infra.db.database import DatabaseRuntime

from app.infra.persistence.research_workbench_repository import ResearchWorkbenchRepository

from app.infra.persistence.research_record_repository import ResearchRecordRepository

from app.infra.persistence.research_alert_repository import ResearchAlertRepository


class ResearchRepository:
    """Compatibility facade; production readers receive the narrow repositories below."""

    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self.workbench = ResearchWorkbenchRepository(database_runtime)
        self.records = ResearchRecordRepository(database_runtime)
        self.alerts = ResearchAlertRepository(database_runtime)

    def delete_record(self, kind: str, record_id: str, expected_version: int) -> None:
        self.records.delete_record(kind, record_id, expected_version)

    def get_workbench(self, *, event_limit: int, note_limit: int) -> dict[str, Any]:
        return self.workbench.get_workbench(event_limit=event_limit, note_limit=note_limit)

    def get_asset_records(self, symbol: str) -> dict[str, Any]:
        return self.workbench.get_asset_records(symbol)

    def list_notes(self, symbol: str, *, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        return self.workbench.list_notes(symbol, offset=offset, limit=limit)

    def list_events(
        self, *, kind: str | None, unacknowledged_only: bool, since: datetime | None, limit: int,
        before: tuple[datetime, datetime, str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        return self.workbench.list_events(kind=kind, unacknowledged_only=unacknowledged_only, since=since, limit=limit, before=before)

    def acknowledge_event(self, event_id: str, acknowledged: bool) -> dict[str, Any]:
        return self.workbench.acknowledge_event(event_id, acknowledged)

    def create_watchlist(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.records.create_watchlist(payload)

    def update_watchlist(self, watchlist_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.records.update_watchlist(watchlist_id, expected_version, payload)

    def set_watchlist_archived(self, watchlist_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return self.records.set_watchlist_archived(watchlist_id, expected_version, archived)

    def create_watch_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.records.create_watch_item(payload)

    def update_watch_item(self, item_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.records.update_watch_item(item_id, expected_version, payload)

    def set_watch_item_archived(self, item_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return self.records.set_watch_item_archived(item_id, expected_version, archived)

    def create_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.records.create_note(payload)

    def update_note(self, note_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.records.update_note(note_id, expected_version, payload)

    def set_note_archived(self, note_id: str, expected_version: int, archived: bool) -> dict[str, Any]:
        return self.records.set_note_archived(note_id, expected_version, archived)

    def create_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.alerts.create_alert(payload)

    def update_alert(self, alert_id: str, expected_version: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.alerts.update_alert(alert_id, expected_version, payload)

    def delete_alert(self, alert_id: str, expected_version: int) -> None:
        self.alerts.delete_alert(alert_id, expected_version)

    def list_enabled_alerts(self) -> list[dict[str, Any]]:
        return self.alerts.list_enabled_alerts()

    def record_alert_evaluation(
        self, alert_id: str, *, value: float, evaluated_at: datetime, expected_version: int
    ) -> dict[str, Any] | None:
        return self.alerts.record_alert_evaluation(
            alert_id, value=value, evaluated_at=evaluated_at, expected_version=expected_version
        )
