from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.domain.portfolios import (
    PortfolioCollectionMismatchError,
    PortfolioCollectionRecord,
    PortfolioDeletedPageRecord,
    PortfolioDeletedSummaryRecord,
    PortfolioExportRecord,
    PortfolioNotFoundError,
    PortfolioRevisionConflictError,
    PortfolioSimulationResultRecord,
    portfolio_simulation_fingerprint,
)
from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import (
    PortfolioCollectionState,
    PortfolioRecord,
    PortfolioSimulationResultRecord as PortfolioSimulationResultRow,
    PortfolioTransactionRecord,
)
from utils.time import utc_now_naive
from uuid import uuid4


COLLECTION_ID = "default"


class PortfolioRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def get_collection(self) -> PortfolioCollectionRecord:
        with self._database_runtime.session_scope() as session:
            state = session.get(PortfolioCollectionState, COLLECTION_ID)
            revision = state.revision if state is not None else 0
            active_portfolio_id = state.active_portfolio_id if state is not None else ""
            records = list(
                session.scalars(
                    select(PortfolioRecord)
                    .where(PortfolioRecord.deleted_at.is_(None))
                    .order_by(
                        PortfolioRecord.position,
                        PortfolioRecord.created_at,
                        PortfolioRecord.id,
                    )
                )
            )
            return self._to_record(
                revision=revision,
                active_portfolio_id=active_portfolio_id,
                records=records,
            )

    def get_ledger_record(self, portfolio_id: str) -> dict:
        with self._database_runtime.session_scope() as session:
            portfolio = self._require_active_portfolio(session, portfolio_id)
            rows = list(
                session.scalars(
                    select(PortfolioTransactionRecord)
                    .where(PortfolioTransactionRecord.portfolio_id == portfolio_id)
                    .order_by(
                        PortfolioTransactionRecord.archived_at.is_not(None),
                        PortfolioTransactionRecord.occurred_at.desc(),
                        PortfolioTransactionRecord.created_at.desc(),
                    )
                )
            )
            return {
                "portfolio_payload": dict(portfolio.payload),
                "transactions": [
                    self._transaction_payload(row)
                    for row in rows
                    if row.archived_at is None
                ],
                "archived_transactions": [
                    self._transaction_payload(row)
                    for row in rows
                    if row.archived_at is not None
                ],
            }

    def create_transaction(self, portfolio_id: str, payload: dict) -> dict:
        with self._database_runtime.session_scope() as session:
            self._require_active_portfolio(session, portfolio_id)
            self._assert_external_id_available(
                session,
                portfolio_id,
                payload.get("external_id"),
            )
            now = utc_now_naive()
            row = PortfolioTransactionRecord(
                id=uuid4().hex,
                portfolio_id=portfolio_id,
                version=1,
                created_at=now,
                updated_at=now,
                **payload,
            )
            session.add(row)
            session.flush()
            return self._transaction_payload(row)

    def update_transaction(
        self,
        portfolio_id: str,
        transaction_id: str,
        expected_version: int,
        payload: dict,
    ) -> dict:
        with self._database_runtime.session_scope() as session:
            self._require_active_portfolio(session, portfolio_id)
            row = self._require_transaction(
                session,
                portfolio_id,
                transaction_id,
                expected_version,
            )
            self._assert_external_id_available(
                session,
                portfolio_id,
                payload.get("external_id"),
                excluding_id=row.id,
            )
            for key, value in payload.items():
                setattr(row, key, value)
            row.version += 1
            row.updated_at = utc_now_naive()
            session.flush()
            return self._transaction_payload(row)

    def set_transaction_archived(
        self,
        portfolio_id: str,
        transaction_id: str,
        expected_version: int,
        archived: bool,
    ) -> dict:
        with self._database_runtime.session_scope() as session:
            self._require_active_portfolio(session, portfolio_id)
            row = self._require_transaction(
                session,
                portfolio_id,
                transaction_id,
                expected_version,
            )
            if not archived:
                self._assert_external_id_available(
                    session,
                    portfolio_id,
                    row.external_id,
                    excluding_id=row.id,
                )
            row.archived_at = utc_now_naive() if archived else None
            row.version += 1
            row.updated_at = utc_now_naive()
            session.flush()
            return self._transaction_payload(row)

    def import_transactions(
        self,
        portfolio_id: str,
        payloads: list[dict],
        *,
        replace: bool,
    ) -> tuple[int, int]:
        with self._database_runtime.session_scope() as session:
            self._require_active_portfolio(session, portfolio_id)
            now = utc_now_naive()
            archived_count = 0
            if replace:
                active_rows = list(
                    session.scalars(
                        select(PortfolioTransactionRecord).where(
                            PortfolioTransactionRecord.portfolio_id == portfolio_id,
                            PortfolioTransactionRecord.archived_at.is_(None),
                        )
                    )
                )
                for row in active_rows:
                    row.archived_at = now
                    row.version += 1
                    row.updated_at = now
                archived_count = len(active_rows)

            batch_external_ids = [
                str(payload["external_id"])
                for payload in payloads
                if payload.get("external_id")
            ]
            if len(batch_external_ids) != len(set(batch_external_ids)):
                raise PortfolioCollectionMismatchError("导入文件中的外部流水编号不能重复")
            if not replace:
                for external_id in batch_external_ids:
                    self._assert_external_id_available(session, portfolio_id, external_id)

            for payload in payloads:
                session.add(
                    PortfolioTransactionRecord(
                        id=uuid4().hex,
                        portfolio_id=portfolio_id,
                        version=1,
                        created_at=now,
                        updated_at=now,
                        **payload,
                    )
                )
            session.flush()
            return len(payloads), archived_count

    @staticmethod
    def _require_active_portfolio(session, portfolio_id: str) -> PortfolioRecord:
        row = session.get(PortfolioRecord, portfolio_id)
        if row is None or row.deleted_at is not None:
            raise PortfolioNotFoundError("没有这个活动组合")
        return row

    @staticmethod
    def _require_transaction(
        session,
        portfolio_id: str,
        transaction_id: str,
        expected_version: int,
    ) -> PortfolioTransactionRecord:
        row = session.get(PortfolioTransactionRecord, transaction_id)
        if row is None or row.portfolio_id != portfolio_id:
            raise PortfolioNotFoundError("组合流水不存在")
        if row.version != expected_version:
            raise PortfolioRevisionConflictError("组合流水已在其它窗口更新，请重新载入后再试")
        return row

    @staticmethod
    def _assert_external_id_available(
        session,
        portfolio_id: str,
        external_id: str | None,
        *,
        excluding_id: str | None = None,
    ) -> None:
        if not external_id:
            return
        statement = select(PortfolioTransactionRecord.id).where(
            PortfolioTransactionRecord.portfolio_id == portfolio_id,
            PortfolioTransactionRecord.external_id == external_id,
            PortfolioTransactionRecord.archived_at.is_(None),
        )
        if excluding_id:
            statement = statement.where(PortfolioTransactionRecord.id != excluding_id)
        if session.scalar(statement) is not None:
            raise PortfolioCollectionMismatchError(f"外部流水编号 {external_id} 已存在")

    @staticmethod
    def _transaction_payload(row: PortfolioTransactionRecord) -> dict:
        return {
            "id": row.id,
            "portfolioId": row.portfolio_id,
            "transactionType": row.transaction_type,
            "symbol": row.symbol,
            "quantity": row.quantity,
            "unitPrice": row.unit_price,
            "cashAmount": row.cash_amount,
            "fee": row.fee,
            "currency": row.currency,
            "feeCurrency": row.fee_currency,
            "externalId": row.external_id,
            "note": row.note,
            "metadata": dict(row.metadata_payload or {}),
            "version": row.version,
            "occurredAt": row.occurred_at,
            "archivedAt": row.archived_at,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }

    def list_deleted(self, *, offset: int, limit: int) -> PortfolioDeletedPageRecord:
        with self._database_runtime.session_scope() as session:
            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(PortfolioRecord)
                    .where(PortfolioRecord.deleted_at.is_not(None))
                )
                or 0
            )
            records = list(
                session.scalars(
                    select(PortfolioRecord)
                    .where(PortfolioRecord.deleted_at.is_not(None))
                    .order_by(
                        PortfolioRecord.deleted_at.desc(),
                        PortfolioRecord.id,
                    )
                    .offset(offset)
                    .limit(limit)
                )
            )
            return PortfolioDeletedPageRecord(
                items=[
                    PortfolioDeletedSummaryRecord(
                        portfolio_id=record.id,
                        name=str(record.payload.get("name") or record.id),
                        deleted_at=record.deleted_at,
                    )
                    for record in records
                ],
                offset=offset,
                limit=limit,
                total=total,
            )

    def get_simulation(self, portfolio_id: str) -> PortfolioSimulationResultRecord:
        with self._database_runtime.session_scope() as session:
            record = session.get(PortfolioRecord, portfolio_id)
            if record is None or record.deleted_at is not None:
                raise PortfolioNotFoundError("没有这个活动组合")
            simulation = session.get(PortfolioSimulationResultRow, portfolio_id)
            if (
                simulation is None
                or simulation.source_fingerprint != portfolio_simulation_fingerprint(record.payload)
            ):
                return PortfolioSimulationResultRecord(portfolio_id, None, None)
            return PortfolioSimulationResultRecord(
                portfolio_id=portfolio_id,
                result_payload=dict(simulation.payload),
                updated_at=simulation.updated_at,
            )

    def save_simulation(
        self,
        portfolio_id: str,
        expected_revision: int,
        result_payload: dict,
    ) -> PortfolioSimulationResultRecord:
        with self._database_runtime.session_scope() as session:
            state = session.get(PortfolioCollectionState, COLLECTION_ID)
            current_revision = state.revision if state is not None else 0
            if current_revision != expected_revision:
                raise PortfolioRevisionConflictError(
                    "组合已在其它窗口更新，请重新载入后再试"
                )
            record = session.get(PortfolioRecord, portfolio_id)
            if record is None or record.deleted_at is not None:
                raise PortfolioNotFoundError("没有这个活动组合")
            now = utc_now_naive()
            simulation = session.get(PortfolioSimulationResultRow, portfolio_id)
            if simulation is None:
                simulation = PortfolioSimulationResultRow(
                    portfolio_id=portfolio_id,
                    created_at=now,
                )
                session.add(simulation)
            simulation.source_fingerprint = portfolio_simulation_fingerprint(record.payload)
            simulation.payload = result_payload
            simulation.updated_at = now
            session.flush()
            return PortfolioSimulationResultRecord(
                portfolio_id=portfolio_id,
                result_payload=dict(simulation.payload),
                updated_at=simulation.updated_at,
            )

    def get_export_record(self) -> PortfolioExportRecord:
        with self._database_runtime.session_scope() as session:
            state = session.get(PortfolioCollectionState, COLLECTION_ID)
            records = list(
                session.scalars(
                    select(PortfolioRecord).order_by(
                        PortfolioRecord.deleted_at.is_not(None),
                        PortfolioRecord.position,
                        PortfolioRecord.created_at,
                        PortfolioRecord.id,
                    )
                )
            )
            simulations = {
                item.portfolio_id: item
                for item in session.scalars(select(PortfolioSimulationResultRow))
            }
            active_payloads = [dict(item.payload) for item in records if item.deleted_at is None]
            deleted_payloads = [dict(item.payload) for item in records if item.deleted_at is not None]
            active_ids = {str(payload["id"]) for payload in active_payloads}
            active_portfolio_id = state.active_portfolio_id if state is not None else ""
            if active_portfolio_id not in active_ids:
                active_portfolio_id = str(active_payloads[0]["id"]) if active_payloads else ""
            return PortfolioExportRecord(
                revision=state.revision if state is not None else 0,
                active_portfolio_id=active_portfolio_id,
                active_payloads=active_payloads,
                deleted_payloads=deleted_payloads,
                simulation_payloads=[
                    (record.id, dict(simulations[record.id].payload))
                    for record in records
                    if record.id in simulations
                    and simulations[record.id].source_fingerprint
                    == portfolio_simulation_fingerprint(record.payload)
                ],
            )

    def apply_collection_changes(
        self,
        active_portfolio_id: str,
        changed_portfolio_payloads: list[dict],
        portfolio_order: list[str],
        expected_revision: int,
    ) -> PortfolioCollectionRecord:
        with self._database_runtime.session_scope() as session:
            now = utc_now_naive()
            revision = self._claim_revision(
                session,
                expected_revision=expected_revision,
                active_portfolio_id=active_portfolio_id,
                updated_at=now,
            )
            existing = {
                record.id: record
                for record in session.scalars(select(PortfolioRecord))
            }
            changed_by_id = {
                str(payload["id"]): payload for payload in changed_portfolio_payloads
            }
            ordered_ids = set(portfolio_order)
            positions = {
                portfolio_id: position
                for position, portfolio_id in enumerate(portfolio_order)
            }

            missing_ids = [
                portfolio_id
                for portfolio_id in portfolio_order
                if portfolio_id not in existing and portfolio_id not in changed_by_id
            ]
            unrestored_ids = [
                portfolio_id
                for portfolio_id in portfolio_order
                if portfolio_id in existing
                and existing[portfolio_id].deleted_at is not None
                and portfolio_id not in changed_by_id
            ]
            if missing_ids or unrestored_ids:
                invalid_ids = missing_ids + unrestored_ids
                raise PortfolioCollectionMismatchError(
                    f"组合变更引用了不存在的活动组合: {', '.join(invalid_ids)}"
                )

            for payload in changed_portfolio_payloads:
                portfolio_id = str(payload["id"])
                record = existing.get(portfolio_id)
                if record is None:
                    record = PortfolioRecord(
                        id=portfolio_id,
                        payload=payload,
                        version=1,
                        position=positions[portfolio_id],
                        deleted_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(record)
                    existing[portfolio_id] = record
                    continue

                changed = (
                    record.payload != payload
                    or record.deleted_at is not None
                )
                simulation_inputs_changed = (
                    portfolio_simulation_fingerprint(record.payload)
                    != portfolio_simulation_fingerprint(payload)
                )
                record.payload = payload
                record.deleted_at = None
                if changed:
                    record.version += 1
                    record.updated_at = now
                if simulation_inputs_changed:
                    session.execute(
                        delete(PortfolioSimulationResultRow).where(
                            PortfolioSimulationResultRow.portfolio_id == portfolio_id
                        )
                    )

            for portfolio_id, record in existing.items():
                if portfolio_id in ordered_ids:
                    position = positions[portfolio_id]
                    if record.position != position:
                        record.position = position
                        record.version += 1
                        record.updated_at = now
                    continue
                if record.deleted_at is not None:
                    continue
                record.deleted_at = now
                record.version += 1
                record.updated_at = now

            session.flush()
            records = list(
                session.scalars(
                    select(PortfolioRecord)
                    .where(PortfolioRecord.deleted_at.is_(None))
                    .order_by(
                        PortfolioRecord.position,
                        PortfolioRecord.created_at,
                        PortfolioRecord.id,
                    )
                )
            )
            return self._to_record(
                revision=revision,
                active_portfolio_id=active_portfolio_id,
                records=records,
            )

    def restore_portfolio(
        self,
        portfolio_id: str,
        expected_revision: int,
    ) -> PortfolioCollectionRecord:
        with self._database_runtime.session_scope() as session:
            now = utc_now_naive()
            revision = self._claim_revision(
                session,
                expected_revision=expected_revision,
                active_portfolio_id=portfolio_id,
                updated_at=now,
            )
            record = session.scalar(
                select(PortfolioRecord)
                .where(PortfolioRecord.id == portfolio_id)
            )
            if record is None or record.deleted_at is None:
                raise PortfolioNotFoundError("回收站中没有这个组合")

            max_position = max(
                (
                    item.position
                    for item in session.scalars(
                        select(PortfolioRecord).where(PortfolioRecord.deleted_at.is_(None))
                    )
                ),
                default=-1,
            )
            record.deleted_at = None
            record.position = max_position + 1
            record.version += 1
            record.updated_at = now
            session.flush()
            records = list(
                session.scalars(
                    select(PortfolioRecord).order_by(
                        PortfolioRecord.deleted_at.is_not(None),
                        PortfolioRecord.position,
                        PortfolioRecord.created_at,
                        PortfolioRecord.id,
                    )
                )
            )
            return self._to_record(
                revision=revision,
                active_portfolio_id=record.id,
                records=records,
            )

    @classmethod
    def _claim_revision(
        cls,
        session,
        *,
        expected_revision: int,
        active_portfolio_id: str,
        updated_at,
    ) -> int:
        cls._ensure_state_row(session, updated_at=updated_at)
        result = session.execute(
            update(PortfolioCollectionState)
            .where(
                PortfolioCollectionState.id == COLLECTION_ID,
                PortfolioCollectionState.revision == expected_revision,
            )
            .values(
                revision=expected_revision + 1,
                active_portfolio_id=active_portfolio_id,
                updated_at=updated_at,
            )
        )
        if result.rowcount != 1:
            raise PortfolioRevisionConflictError(
                "组合已在其它窗口更新，请重新载入后再试"
            )
        return expected_revision + 1

    @staticmethod
    def _ensure_state_row(session, *, updated_at) -> None:
        values = {
            "id": COLLECTION_ID,
            "revision": 0,
            "active_portfolio_id": None,
            "updated_at": updated_at,
        }
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "sqlite":
            statement = sqlite_insert(PortfolioCollectionState).values(**values)
            session.execute(statement.on_conflict_do_nothing(index_elements=["id"]))
            return
        if dialect_name == "postgresql":
            statement = postgresql_insert(PortfolioCollectionState).values(**values)
            session.execute(statement.on_conflict_do_nothing(index_elements=["id"]))
            return
        if session.get(PortfolioCollectionState, COLLECTION_ID) is None:
            session.add(PortfolioCollectionState(**values))
            session.flush()

    @staticmethod
    def _to_record(
        *,
        revision: int,
        active_portfolio_id: str,
        records: list[PortfolioRecord],
    ) -> PortfolioCollectionRecord:
        active = [dict(record.payload) for record in records if record.deleted_at is None]

        active_ids = {str(portfolio["id"]) for portfolio in active}
        resolved_active_id = active_portfolio_id if active_portfolio_id in active_ids else (str(active[0]["id"]) if active else "")
        return PortfolioCollectionRecord(
            revision=revision,
            active_portfolio_id=resolved_active_id,
            active_payloads=active,
        )
