from __future__ import annotations

from app.application.persistence_ports import TradeSignalRepositoryPort
from app.contracts.research import (
    ResearchArchiveCommand,
    TradeSignalPageResponse,
    TradeSignalResponse,
    TradeSignalStatsResponse,
)


class TradeSignalService:
    def __init__(self, repository: TradeSignalRepositoryPort) -> None:
        self._repository = repository

    def list_signals(
        self,
        *,
        symbol: str | None,
        outcome_status: str | None,
        source: str | None,
        include_archived: bool,
        offset: int,
        limit: int,
    ) -> TradeSignalPageResponse:
        rows, total = self._repository.list_signals(
            symbol=symbol,
            outcome_status=outcome_status,
            source=source,
            include_archived=include_archived,
            offset=offset,
            limit=limit,
        )
        return TradeSignalPageResponse(items=rows, total=total, offset=offset, limit=limit)

    def get_stats(self) -> TradeSignalStatsResponse:
        return TradeSignalStatsResponse.model_validate(self._repository.get_stats())

    def archive(
        self,
        signal_id: str,
        command: ResearchArchiveCommand,
        *,
        archived: bool,
    ) -> TradeSignalResponse:
        return TradeSignalResponse.model_validate(
            self._repository.set_signal_archived(
                signal_id,
                command.expectedVersion,
                archived,
            )
        )
