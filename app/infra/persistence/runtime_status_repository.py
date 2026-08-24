from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import RuntimeComponentStatus
from utils.time import utc_now_naive


BACKGROUND_COMPONENT = "background-worker"
MARKET_INDICATORS_COMPONENT = "market-indicators"


@dataclass(frozen=True, slots=True)
class RuntimeStatusSnapshot:
    component: str
    owner_id: str
    status: str
    started_at: datetime
    heartbeat_at: datetime
    last_success_at: datetime | None
    last_failure_at: datetime | None
    next_run_at: datetime | None
    error_code: str | None
    error_detail: str | None


class RuntimeStatusRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def get(self, component: str) -> RuntimeStatusSnapshot | None:
        with self._database_runtime.session_scope() as session:
            record = session.get(RuntimeComponentStatus, component)
            return self._snapshot(record) if record is not None else None

    def get_many(self, components: tuple[str, ...]) -> dict[str, RuntimeStatusSnapshot]:
        if not components:
            return {}
        with self._database_runtime.session_scope() as session:
            records = session.scalars(
                select(RuntimeComponentStatus).where(
                    RuntimeComponentStatus.component.in_(components)
                )
            )
            return {
                record.component: self._snapshot(record)
                for record in records
            }

    def mark_starting(self, component: str, owner_id: str) -> None:
        now = utc_now_naive()
        self._upsert(
            component,
            owner_id,
            status="starting",
            started_at=now,
            heartbeat_at=now,
            error_code=None,
            error_detail=None,
        )

    def mark_ready(self, component: str, owner_id: str) -> None:
        self._update_owned(component, owner_id, status="ready")

    def heartbeat(self, component: str, owner_id: str) -> None:
        self._update_owned(component, owner_id)

    def mark_running(
        self,
        component: str,
        owner_id: str,
        *,
        next_run_at: datetime | None = None,
    ) -> None:
        now = utc_now_naive()
        self._upsert(
            component,
            owner_id,
            status="running",
            started_at=now,
            heartbeat_at=now,
            next_run_at=next_run_at,
            error_code=None,
            error_detail=None,
            preserve_history=True,
        )

    def mark_success(
        self,
        component: str,
        owner_id: str,
        *,
        next_run_at: datetime | None = None,
    ) -> None:
        self._update_owned(
            component,
            owner_id,
            status="ready",
            last_success_at=utc_now_naive(),
            next_run_at=next_run_at,
            error_code=None,
            error_detail=None,
        )

    def mark_failed(
        self,
        component: str,
        owner_id: str,
        *,
        error_code: str,
        error_detail: str,
        next_run_at: datetime | None = None,
    ) -> None:
        self._update_owned(
            component,
            owner_id,
            status="failed",
            last_failure_at=utc_now_naive(),
            next_run_at=next_run_at,
            error_code=error_code[:80],
            error_detail=error_detail[:2_000],
        )

    def mark_stopped(self, component: str, owner_id: str) -> None:
        self._update_owned(component, owner_id, status="stopped")

    def _upsert(
        self,
        component: str,
        owner_id: str,
        *,
        status: str,
        started_at: datetime,
        heartbeat_at: datetime,
        last_success_at: datetime | None = None,
        last_failure_at: datetime | None = None,
        next_run_at: datetime | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        preserve_history: bool = False,
    ) -> None:
        with self._database_runtime.session_scope() as session:
            record = session.get(RuntimeComponentStatus, component)
            if record is None:
                record = RuntimeComponentStatus(component=component)
                session.add(record)
            record.owner_id = owner_id
            record.status = status
            record.started_at = started_at
            record.heartbeat_at = heartbeat_at
            if not preserve_history:
                record.last_success_at = last_success_at
                record.last_failure_at = last_failure_at
            record.next_run_at = next_run_at
            record.error_code = error_code
            record.error_detail = error_detail
            record.updated_at = heartbeat_at

    def _update_owned(self, component: str, owner_id: str, **changes) -> None:
        now = utc_now_naive()
        with self._database_runtime.session_scope() as session:
            record = session.get(RuntimeComponentStatus, component)
            if record is None or record.owner_id != owner_id:
                return
            record.heartbeat_at = now
            record.updated_at = now
            for field, value in changes.items():
                setattr(record, field, value)

    @staticmethod
    def _snapshot(record: RuntimeComponentStatus) -> RuntimeStatusSnapshot:
        return RuntimeStatusSnapshot(
            component=record.component,
            owner_id=record.owner_id,
            status=record.status,
            started_at=record.started_at,
            heartbeat_at=record.heartbeat_at,
            last_success_at=record.last_success_at,
            last_failure_at=record.last_failure_at,
            next_run_at=record.next_run_at,
            error_code=record.error_code,
            error_detail=record.error_detail,
        )
