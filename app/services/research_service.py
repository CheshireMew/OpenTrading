from __future__ import annotations

from datetime import datetime
from typing import Any

from app.application.persistence_ports import ResearchRepositoryPort
from app.contracts.research import (
    ResearchAlertCreateCommand,
    ResearchAlertResponse,
    ResearchAlertUpdateCommand,
    ResearchArchiveCommand,
    ResearchEventAcknowledgeCommand,
    ResearchEventPageResponse,
    ResearchEventResponse,
    ResearchNoteCreateCommand,
    ResearchNoteResponse,
    ResearchNoteUpdateCommand,
    ResearchWatchItemCreateCommand,
    ResearchWatchItemResponse,
    ResearchWatchItemUpdateCommand,
    ResearchWatchlistCreateCommand,
    ResearchWatchlistResponse,
    ResearchWatchlistUpdateCommand,
    ResearchWorkbenchResponse,
)


class ResearchService:
    def __init__(self, repository: ResearchRepositoryPort) -> None:
        self._repository = repository

    def get_workbench(self, *, event_limit: int, note_limit: int) -> ResearchWorkbenchResponse:
        return ResearchWorkbenchResponse.model_validate(
            self._repository.get_workbench(event_limit=event_limit, note_limit=note_limit)
        )

    def list_events(
        self,
        *,
        kind: str | None,
        unacknowledged_only: bool,
        since: datetime | None,
        limit: int,
    ) -> ResearchEventPageResponse:
        rows, total = self._repository.list_events(
            kind=kind,
            unacknowledged_only=unacknowledged_only,
            since=since,
            limit=limit,
        )
        return ResearchEventPageResponse(items=rows, total=total)

    def create_watchlist(self, command: ResearchWatchlistCreateCommand) -> ResearchWatchlistResponse:
        return ResearchWatchlistResponse.model_validate(self._repository.create_watchlist(command.model_dump()))

    def update_watchlist(self, watchlist_id: str, command: ResearchWatchlistUpdateCommand) -> ResearchWatchlistResponse:
        payload = command.model_dump(exclude={"expectedVersion"})
        return ResearchWatchlistResponse.model_validate(
            self._repository.update_watchlist(watchlist_id, command.expectedVersion, payload)
        )

    def archive_watchlist(
        self, watchlist_id: str, command: ResearchArchiveCommand, *, archived: bool
    ) -> ResearchWatchlistResponse:
        return ResearchWatchlistResponse.model_validate(
            self._repository.set_watchlist_archived(watchlist_id, command.expectedVersion, archived)
        )

    def create_watch_item(self, command: ResearchWatchItemCreateCommand) -> ResearchWatchItemResponse:
        return ResearchWatchItemResponse.model_validate(
            self._repository.create_watch_item(self._watch_item_payload(command))
        )

    def update_watch_item(self, item_id: str, command: ResearchWatchItemUpdateCommand) -> ResearchWatchItemResponse:
        return ResearchWatchItemResponse.model_validate(
            self._repository.update_watch_item(
                item_id,
                command.expectedVersion,
                self._watch_item_payload(command),
            )
        )

    def archive_watch_item(
        self, item_id: str, command: ResearchArchiveCommand, *, archived: bool
    ) -> ResearchWatchItemResponse:
        return ResearchWatchItemResponse.model_validate(
            self._repository.set_watch_item_archived(item_id, command.expectedVersion, archived)
        )

    def create_note(self, command: ResearchNoteCreateCommand) -> ResearchNoteResponse:
        return ResearchNoteResponse.model_validate(self._repository.create_note(self._note_payload(command)))

    def update_note(self, note_id: str, command: ResearchNoteUpdateCommand) -> ResearchNoteResponse:
        return ResearchNoteResponse.model_validate(
            self._repository.update_note(
                note_id,
                command.expectedVersion,
                self._note_payload(command),
            )
        )

    def archive_note(self, note_id: str, command: ResearchArchiveCommand, *, archived: bool) -> ResearchNoteResponse:
        return ResearchNoteResponse.model_validate(
            self._repository.set_note_archived(note_id, command.expectedVersion, archived)
        )

    def create_alert(self, command: ResearchAlertCreateCommand) -> ResearchAlertResponse:
        return ResearchAlertResponse.model_validate(self._repository.create_alert(self._alert_payload(command)))

    def update_alert(self, alert_id: str, command: ResearchAlertUpdateCommand) -> ResearchAlertResponse:
        return ResearchAlertResponse.model_validate(
            self._repository.update_alert(
                alert_id,
                command.expectedVersion,
                self._alert_payload(command),
            )
        )

    def archive_alert(self, alert_id: str, command: ResearchArchiveCommand, *, archived: bool) -> ResearchAlertResponse:
        return ResearchAlertResponse.model_validate(
            self._repository.set_alert_archived(alert_id, command.expectedVersion, archived)
        )

    def acknowledge_event(self, event_id: str, command: ResearchEventAcknowledgeCommand) -> ResearchEventResponse:
        return ResearchEventResponse.model_validate(self._repository.acknowledge_event(event_id, command.acknowledged))

    @classmethod
    def _watch_item_payload(cls, command: ResearchWatchItemCreateCommand) -> dict[str, Any]:
        return {
            "watchlist_id": command.watchlistId,
            "symbol": cls._normalize_symbol(command.symbol, command.assetClass),
            "asset_class": command.assetClass,
            "display_name": command.displayName.strip(),
            "thesis": command.thesis.strip(),
            "target_price": command.targetPrice,
            "invalidation_price": command.invalidationPrice,
            "tags": command.tags,
            "source_context": command.sourceContext,
        }

    @classmethod
    def _note_payload(cls, command: ResearchNoteCreateCommand) -> dict[str, Any]:
        return {
            "watch_item_id": command.watchItemId,
            "symbol": cls._normalize_symbol(command.symbol),
            "kind": command.kind,
            "title": command.title.strip(),
            "content": command.content.strip(),
            "snapshot": command.snapshot,
            "occurred_at": command.occurredAt,
        }

    @classmethod
    def _alert_payload(cls, command: ResearchAlertCreateCommand) -> dict[str, Any]:
        return {
            "watch_item_id": command.watchItemId,
            "symbol": cls._normalize_symbol(command.symbol),
            "name": command.name.strip(),
            "metric": command.metric.strip(),
            "operator": command.operator,
            "threshold": command.threshold,
            "secondary_threshold": command.secondaryThreshold,
            "enabled": int(command.enabled),
            "cooldown_minutes": command.cooldownMinutes,
            "notification_channels": command.notificationChannels,
            "configuration": command.configuration,
        }

    @staticmethod
    def _normalize_symbol(symbol: str, asset_class: str = "crypto") -> str:
        value = symbol.strip()
        return value if asset_class == "web3" else value.upper()
