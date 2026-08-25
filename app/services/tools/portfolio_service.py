from __future__ import annotations

from datetime import datetime, timezone

from app.application.persistence_ports import PortfolioRepositoryPort
from app.domain.portfolio_accounting import calculate_portfolio_ledger
from app.contracts.portfolios import (
    LegacyPortfolioExportDocument,
    PortfolioBalancePortfolio,
    PortfolioBalanceSnapshot,
    PortfolioCollectionChangeCommand,
    PortfolioCollectionImportCommand,
    PortfolioCollectionResponse,
    PortfolioCollectionSaveCommand,
    PortfolioDeletedPage,
    PortfolioDeletedSummary,
    PortfolioExportDocument,
    PortfolioSimulationArtifact,
    PortfolioSimulationResultCommand,
    PortfolioSimulationResultResponse,
    PortfolioLedgerResponse,
    PortfolioTransactionArchiveCommand,
    PortfolioTransactionCreateCommand,
    PortfolioTransactionImportCommand,
    PortfolioTransactionImportResponse,
    PortfolioTransactionResponse,
    PortfolioTransactionUpdateCommand,
)


class PortfolioService:
    def __init__(self, repository: PortfolioRepositoryPort) -> None:
        self._repository = repository

    def get_collection(self) -> PortfolioCollectionResponse:
        return self._to_response(self._repository.get_collection())

    def get_ledger(self, portfolio_id: str) -> PortfolioLedgerResponse:
        record = self._repository.get_ledger_record(portfolio_id)
        return self._ledger_response(portfolio_id, record)

    def create_transaction(
        self,
        portfolio_id: str,
        command: PortfolioTransactionCreateCommand,
    ) -> PortfolioTransactionResponse:
        return PortfolioTransactionResponse.model_validate(
            self._repository.create_transaction(
                portfolio_id,
                self._transaction_payload(command),
            )
        )

    def update_transaction(
        self,
        portfolio_id: str,
        transaction_id: str,
        command: PortfolioTransactionUpdateCommand,
    ) -> PortfolioTransactionResponse:
        return PortfolioTransactionResponse.model_validate(
            self._repository.update_transaction(
                portfolio_id,
                transaction_id,
                command.expectedVersion,
                self._transaction_payload(command),
            )
        )

    def archive_transaction(
        self,
        portfolio_id: str,
        transaction_id: str,
        command: PortfolioTransactionArchiveCommand,
        *,
        archived: bool,
    ) -> PortfolioTransactionResponse:
        return PortfolioTransactionResponse.model_validate(
            self._repository.set_transaction_archived(
                portfolio_id,
                transaction_id,
                command.expectedVersion,
                archived,
            )
        )

    def import_transactions(
        self,
        portfolio_id: str,
        command: PortfolioTransactionImportCommand,
    ) -> PortfolioTransactionImportResponse:
        imported_count, archived_count = self._repository.import_transactions(
            portfolio_id,
            [self._transaction_payload(item) for item in command.transactions],
            replace=command.mode == "replace",
        )
        return PortfolioTransactionImportResponse(
            importedCount=imported_count,
            archivedCount=archived_count,
            ledger=self.get_ledger(portfolio_id),
        )

    def save_collection(self, command: PortfolioCollectionSaveCommand) -> PortfolioCollectionResponse:
        return self._to_response(
            self._repository.apply_collection_changes(
                command.snapshot.activePortfolioId,
                [portfolio.model_dump(mode="json") for portfolio in command.snapshot.portfolios],
                [portfolio.id for portfolio in command.snapshot.portfolios],
                command.expectedRevision,
            )
        )

    def apply_collection_changes(
        self,
        command: PortfolioCollectionChangeCommand,
    ) -> PortfolioCollectionResponse:
        return self._to_response(
            self._repository.apply_collection_changes(
                command.activePortfolioId,
                [portfolio.model_dump(mode="json") for portfolio in command.changedPortfolios],
                command.portfolioOrder,
                command.expectedRevision,
            )
        )

    def restore_portfolio(self, portfolio_id: str, expected_revision: int) -> PortfolioCollectionResponse:
        return self._to_response(
            self._repository.restore_portfolio(portfolio_id, expected_revision)
        )

    def list_deleted(self, *, offset: int, limit: int) -> PortfolioDeletedPage:
        page = self._repository.list_deleted(offset=offset, limit=limit)
        return PortfolioDeletedPage(
            items=[
                PortfolioDeletedSummary(
                    id=item.portfolio_id,
                    name=item.name,
                    deletedAt=item.deleted_at,
                )
                for item in page.items
            ],
            offset=page.offset,
            limit=page.limit,
            total=page.total,
        )

    def get_simulation(self, portfolio_id: str) -> PortfolioSimulationResultResponse:
        return self._to_simulation_response(
            self._repository.get_simulation(portfolio_id)
        )

    def save_simulation(
        self,
        portfolio_id: str,
        command: PortfolioSimulationResultCommand,
    ) -> PortfolioSimulationResultResponse:
        return self._to_simulation_response(
            self._repository.save_simulation(
                portfolio_id,
                command.expectedRevision,
                command.result.model_dump(mode="json"),
            )
        )

    def export_collection(self) -> PortfolioExportDocument:
        record = self._repository.get_export_record()
        return PortfolioExportDocument(
            schemaVersion=2,
            exportedAt=datetime.now(timezone.utc),
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId=record.active_portfolio_id,
                portfolios=record.active_payloads,
            ),
            deletedPortfolios=record.deleted_payloads,
            simulationResults=[
                PortfolioSimulationArtifact(portfolioId=portfolio_id, result=payload)
                for portfolio_id, payload in record.simulation_payloads
            ],
        )

    def import_collection(self, command: PortfolioCollectionImportCommand) -> PortfolioCollectionResponse:
        imported_snapshot, imported_simulations = self._normalize_import_document(
            command.document
        )
        if command.mode == "replace":
            snapshot = imported_snapshot
        else:
            current = self.get_collection()
            merged = {portfolio.id: portfolio for portfolio in current.snapshot.portfolios}
            for portfolio in imported_snapshot.portfolios:
                merged[portfolio.id] = portfolio
            ordered_ids = [portfolio.id for portfolio in current.snapshot.portfolios]
            ordered_ids.extend(
                portfolio.id
                for portfolio in imported_snapshot.portfolios
                if portfolio.id not in set(ordered_ids)
            )
            portfolios = [merged[portfolio_id] for portfolio_id in ordered_ids]
            imported_active = imported_snapshot.activePortfolioId
            active_id = imported_active if imported_active in merged else current.snapshot.activePortfolioId
            snapshot = PortfolioBalanceSnapshot(
                activePortfolioId=active_id,
                portfolios=portfolios,
            )
        record = self._repository.apply_collection_changes(
            snapshot.activePortfolioId,
            [portfolio.model_dump(mode="json") for portfolio in snapshot.portfolios],
            [portfolio.id for portfolio in snapshot.portfolios],
            command.expectedRevision,
        )
        active_ids = {portfolio.id for portfolio in snapshot.portfolios}
        for portfolio_id, result in imported_simulations.items():
            if portfolio_id not in active_ids:
                continue
            self._repository.save_simulation(
                portfolio_id,
                record.revision,
                result.model_dump(mode="json"),
            )
        return self._to_response(record)

    @staticmethod
    def _normalize_import_document(document):
        if isinstance(document, LegacyPortfolioExportDocument):
            portfolios = [
                PortfolioBalancePortfolio.model_validate(
                    portfolio.model_dump(exclude={"lastSimulationResult"})
                )
                for portfolio in document.snapshot.portfolios
            ]
            simulations = {
                portfolio.id: portfolio.lastSimulationResult
                for portfolio in document.snapshot.portfolios
                if portfolio.lastSimulationResult is not None
            }
            return (
                PortfolioBalanceSnapshot(
                    activePortfolioId=document.snapshot.activePortfolioId,
                    portfolios=portfolios,
                ),
                simulations,
            )
        return (
            document.snapshot,
            {
                artifact.portfolioId: artifact.result
                for artifact in document.simulationResults
            },
        )

    @staticmethod
    def _to_response(record) -> PortfolioCollectionResponse:
        return PortfolioCollectionResponse(
            revision=record.revision,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId=record.active_portfolio_id,
                portfolios=record.active_payloads,
            ),
        )

    @staticmethod
    def _to_simulation_response(record) -> PortfolioSimulationResultResponse:
        return PortfolioSimulationResultResponse(
            portfolioId=record.portfolio_id,
            result=record.result_payload,
            updatedAt=record.updated_at,
        )

    @staticmethod
    def _transaction_payload(command: PortfolioTransactionCreateCommand) -> dict:
        return {
            "transaction_type": command.transactionType,
            "symbol": command.symbol.strip().upper(),
            "quantity": command.quantity,
            "unit_price": command.unitPrice,
            "cash_amount": command.cashAmount,
            "fee": command.fee,
            "currency": command.currency.strip().upper(),
            "fee_currency": command.feeCurrency.strip().upper(),
            "external_id": command.externalId.strip() if command.externalId else None,
            "note": command.note.strip(),
            "metadata_payload": command.metadata,
            "occurred_at": command.occurredAt.astimezone(timezone.utc).replace(tzinfo=None)
            if command.occurredAt.tzinfo is not None
            else command.occurredAt,
        }

    @staticmethod
    def _ledger_response(portfolio_id: str, record: dict) -> PortfolioLedgerResponse:
        portfolio_payload = record["portfolio_payload"]
        market_prices = {
            str(asset.get("symbol") or "").upper(): float(asset.get("currentPrice") or 0)
            for asset in portfolio_payload.get("assets", [])
            if asset.get("symbol")
        }
        active_transactions = record["transactions"]
        domain_transactions = [
            {
                "id": item["id"],
                "transaction_type": item["transactionType"],
                "symbol": item["symbol"],
                "quantity": item["quantity"],
                "unit_price": item["unitPrice"],
                "cash_amount": item["cashAmount"],
                "fee": item["fee"],
                "occurred_at": item["occurredAt"],
            }
            for item in active_transactions
        ]
        summary = calculate_portfolio_ledger(
            domain_transactions,
            market_prices=market_prices,
        )
        return PortfolioLedgerResponse(
            portfolioId=portfolio_id,
            transactions=active_transactions,
            archivedTransactions=record["archived_transactions"],
            summary=summary,
        )
