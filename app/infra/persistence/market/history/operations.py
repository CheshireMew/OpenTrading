from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.infra.persistence.market.history.sql import CatalogConnection, CatalogRow
from app.infra.persistence.market.history.codec import json_dumps, json_loads
from app.infra.persistence.market.history.database import MarketHistoryDatabase


FINAL_JOB_STATUSES = {
    "success", "warning", "blocked", "error", "interrupted", "cancelled",
}


class OperationRepository:
    """Owns persisted job definitions, occurrences, attempts, leases, and events."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self.database = database

    def create_job(
        self,
        *,
        job_id: str,
        task: str,
        interval_minutes: int,
        created_at: datetime,
    ) -> dict[str, Any]:
        timestamp = _utc(created_at)
        try:
            with self.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO jobs(
                        job_id, task, interval_minutes, enabled, version,
                        next_run_at, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, 1, ?, ?, ?)
                    """,
                    (job_id, task, interval_minutes, timestamp, timestamp, timestamp),
                )
        except IntegrityError as exc:
            raise RuntimeError(f"job already exists: {job_id}") from exc
        return self.job(job_id)

    def job(self, job_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"job does not exist: {job_id}")
        return _job_payload(row)

    def jobs(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at, job_id").fetchall()
        return [_job_payload(row) for row in rows]

    def set_enabled(self, job_id: str, enabled: bool, *, changed_at: datetime) -> dict[str, Any]:
        timestamp = _utc(changed_at)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise ValueError(f"job does not exist: {job_id}")
            if bool(row["enabled"]) != enabled:
                connection.execute(
                    """
                    UPDATE jobs
                    SET enabled = ?, version = version + 1,
                        next_run_at = CASE WHEN ? = 1 THEN ? ELSE next_run_at END,
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    (int(enabled), int(enabled), timestamp, timestamp, job_id),
                )
        return self.job(job_id)

    def due_jobs(self, *, now: datetime) -> list[dict[str, Any]]:
        timestamp = _utc(now)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                WHERE enabled = 1 AND next_run_at <= ?
                ORDER BY next_run_at, created_at, job_id
                """,
                (timestamp,),
            ).fetchall()
        return [_job_payload(row) for row in rows]

    def claim_manual(
        self,
        job_id: str,
        *,
        now: datetime,
        worker_id: str,
        lease_seconds: int,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_expired(connection, now=now)
            job = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if job is None:
                raise ValueError(f"job does not exist: {job_id}")
            return self._claim(
                connection,
                job=job,
                scheduled_at=now,
                trigger="manual",
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )

    def claim_due(
        self,
        job_id: str,
        *,
        now: datetime,
        worker_id: str,
        lease_seconds: int,
    ) -> dict[str, Any] | None:
        timestamp = _utc(now)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_expired(connection, now=now)
            job = connection.execute(
                """
                SELECT * FROM jobs
                WHERE job_id = ? AND enabled = 1 AND next_run_at <= ?
                """,
                (job_id, timestamp),
            ).fetchone()
            if job is None:
                return None
            scheduled_at = datetime.fromisoformat(job["next_run_at"])
            next_run_at = scheduled_at + timedelta(minutes=int(job["interval_minutes"]))
            while next_run_at <= now:
                next_run_at += timedelta(minutes=int(job["interval_minutes"]))
            connection.execute(
                "UPDATE jobs SET next_run_at = ?, updated_at = ? WHERE job_id = ?",
                (_utc(next_run_at), timestamp, job_id),
            )
            return self._claim(
                connection,
                job=job,
                scheduled_at=scheduled_at,
                trigger="scheduled",
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )

    def _claim(
        self,
        connection: CatalogConnection,
        *,
        job: CatalogRow,
        scheduled_at: datetime,
        trigger: str,
        worker_id: str,
        lease_seconds: int,
    ) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        started_at = _utc(started)
        scheduled_text = _utc(scheduled_at)
        if trigger == "scheduled":
            identity = f"{job['job_id']}:{job['version']}:{scheduled_text}"
            occurrence_id = f"scheduled-{sha256(identity.encode('utf-8')).hexdigest()[:24]}"
        else:
            occurrence_id = f"manual-{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO job_occurrences(
                occurrence_id, job_id, job_version, scheduled_at, trigger,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                occurrence_id, job["job_id"], job["version"], scheduled_text,
                trigger, started_at, started_at,
            ),
        )
        active = connection.execute(
            "SELECT * FROM task_leases WHERE task = ? AND lease_expires_at > ?",
            (job["task"], started_at),
        ).fetchone()
        run_id = f"job-{started.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
        if active is not None:
            details = {
                "active_run_id": active["owner_run_id"],
                "active_worker_id": active["worker_id"],
                "lease_expires_at": active["lease_expires_at"],
            }
            connection.execute(
                """
                INSERT INTO job_runs(
                    run_id, occurrence_id, attempt, job_id, task, worker_id,
                    lease_expires_at, heartbeat_at, started_at, finished_at,
                    status, summary, details_json
                ) VALUES (?, ?, 1, ?, ?, ?, NULL, NULL, ?, ?, 'blocked', ?, ?)
                """,
                (
                    run_id, occurrence_id, job["job_id"], job["task"], worker_id,
                    started_at, started_at, f"{job['task']} is already running",
                    json_dumps(details),
                ),
            )
            connection.execute(
                """
                UPDATE job_occurrences
                SET status = 'blocked', updated_at = ? WHERE occurrence_id = ?
                """,
                (started_at, occurrence_id),
            )
            self._append_event(
                connection,
                occurred_at=started_at,
                level="warning",
                component="operations.scheduler",
                event="job_claim",
                result="blocked",
                correlation_id=run_id,
                parent_correlation_id=occurrence_id,
                details=details,
            )
            return self._run(connection, run_id)

        lease_expires_at = _utc(started + timedelta(seconds=lease_seconds))
        connection.execute(
            """
            INSERT INTO job_runs(
                run_id, occurrence_id, attempt, job_id, task, worker_id,
                lease_expires_at, heartbeat_at, started_at, finished_at,
                status, summary, details_json
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, NULL, 'running', '', '{}')
            """,
            (
                run_id, occurrence_id, job["job_id"], job["task"], worker_id,
                lease_expires_at, started_at, started_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO task_leases(task, owner_run_id, worker_id, lease_expires_at, heartbeat_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(task) DO UPDATE SET
                owner_run_id = excluded.owner_run_id,
                worker_id = excluded.worker_id,
                lease_expires_at = excluded.lease_expires_at,
                heartbeat_at = excluded.heartbeat_at
            """,
            (job["task"], run_id, worker_id, lease_expires_at, started_at),
        )
        connection.execute(
            """
            UPDATE job_occurrences
            SET status = 'running', updated_at = ? WHERE occurrence_id = ?
            """,
            (started_at, occurrence_id),
        )
        self._append_event(
            connection,
            occurred_at=started_at,
            level="info",
            component="operations.scheduler",
            event="job_claim",
            result="running",
            correlation_id=run_id,
            parent_correlation_id=occurrence_id,
            details={"worker_id": worker_id, "lease_expires_at": lease_expires_at},
        )
        return self._run(connection, run_id)

    def heartbeat(
        self,
        run_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        timestamp = _utc(now)
        lease_expires_at = _utc(now + timedelta(seconds=lease_seconds))
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE job_runs
                SET heartbeat_at = ?, lease_expires_at = ?
                WHERE run_id = ? AND worker_id = ? AND status = 'running'
                """,
                (timestamp, lease_expires_at, run_id, worker_id),
            ).rowcount
            if updated:
                connection.execute(
                    """
                    UPDATE task_leases
                    SET heartbeat_at = ?, lease_expires_at = ?
                    WHERE owner_run_id = ? AND worker_id = ?
                    """,
                    (timestamp, lease_expires_at, run_id, worker_id),
                )
        return bool(updated)

    def complete(
        self,
        run_id: str,
        *,
        worker_id: str,
        status: str,
        summary: str,
        details: dict[str, object],
        finished_at: datetime,
    ) -> dict[str, Any]:
        if status not in FINAL_JOB_STATUSES:
            raise ValueError(f"invalid final job status: {status}")
        timestamp = _utc(finished_at)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT occurrence_id, task FROM job_runs WHERE run_id = ?", (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"job run does not exist: {run_id}")
            updated = connection.execute(
                """
                UPDATE job_runs
                SET finished_at = ?, status = ?, summary = ?, details_json = ?,
                    lease_expires_at = NULL
                WHERE run_id = ? AND worker_id = ? AND status = 'running'
                """,
                (timestamp, status, summary, json_dumps(details), run_id, worker_id),
            ).rowcount
            if updated != 1:
                raise RuntimeError(f"job run is no longer owned by this worker: {run_id}")
            connection.execute(
                """
                UPDATE job_occurrences SET status = ?, updated_at = ? WHERE occurrence_id = ?
                """,
                (status, timestamp, row["occurrence_id"]),
            )
            connection.execute(
                "DELETE FROM task_leases WHERE task = ? AND owner_run_id = ? AND worker_id = ?",
                (row["task"], run_id, worker_id),
            )
            level = "error" if status in {"error", "interrupted"} else (
                "warning" if status in {"warning", "blocked", "cancelled"} else "info"
            )
            self._append_event(
                connection,
                occurred_at=timestamp,
                level=level,
                component="operations.scheduler",
                event="job_terminal",
                result=status,
                correlation_id=run_id,
                parent_correlation_id=row["occurrence_id"],
                details={"summary": summary, **details},
            )
            return self._run(connection, run_id)

    def recover_expired(self, *, now: datetime) -> int:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._recover_expired(connection, now=now)

    def _recover_expired(self, connection: CatalogConnection, *, now: datetime) -> int:
        timestamp = _utc(now)
        rows = connection.execute(
            """
            SELECT run_id, occurrence_id, task FROM job_runs
            WHERE status = 'running' AND lease_expires_at <= ?
            """,
            (timestamp,),
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE job_runs
                SET status = 'interrupted', finished_at = ?, lease_expires_at = NULL,
                    summary = 'worker lease expired before a terminal result was committed'
                WHERE run_id = ? AND status = 'running'
                """,
                (timestamp, row["run_id"]),
            )
            connection.execute(
                """
                UPDATE job_occurrences SET status = 'interrupted', updated_at = ?
                WHERE occurrence_id = ?
                """,
                (timestamp, row["occurrence_id"]),
            )
            connection.execute(
                "DELETE FROM task_leases WHERE task = ? AND owner_run_id = ?",
                (row["task"], row["run_id"]),
            )
            self._append_event(
                connection,
                occurred_at=timestamp,
                level="error",
                component="operations.scheduler",
                event="job_recovery",
                result="interrupted",
                correlation_id=row["run_id"],
                parent_correlation_id=row["occurrence_id"],
                details={"reason": "lease_expired", "replayed": False},
            )
        return len(rows)

    def runs(self, *, job_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        where = ""
        parameters: list[Any] = []
        if job_id is not None:
            where = "WHERE job_runs.job_id = ?"
            parameters.append(job_id)
        parameters.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT job_runs.*, job_occurrences.scheduled_at, job_occurrences.trigger
                FROM job_runs
                JOIN job_occurrences USING(occurrence_id)
                {where}
                ORDER BY job_runs.started_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [_run_payload(row) for row in rows]

    def latest_runs(self) -> dict[str, dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT job_runs.*, job_occurrences.scheduled_at, job_occurrences.trigger,
                           ROW_NUMBER() OVER (
                               PARTITION BY job_runs.job_id ORDER BY job_runs.started_at DESC
                           ) AS position
                    FROM job_runs
                    JOIN job_occurrences USING(occurrence_id)
                )
                WHERE position = 1
                """
            ).fetchall()
        return {row["job_id"]: _run_payload(row) for row in rows}

    def append_event(
        self,
        *,
        level: str,
        component: str,
        event: str,
        result: str,
        correlation_id: str,
        details: dict[str, Any],
        parent_correlation_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> int:
        with self.database.connect() as connection:
            return self._append_event(
                connection,
                occurred_at=_utc(occurred_at or datetime.now(timezone.utc)),
                level=level,
                component=component,
                event=event,
                result=result,
                correlation_id=correlation_id,
                parent_correlation_id=parent_correlation_id,
                details=details,
            )

    def events(self, *, correlation_id: str, limit: int = 200) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM operation_events
                WHERE correlation_id = ?
                ORDER BY event_id
                LIMIT ?
                """,
                (correlation_id, limit),
            ).fetchall()
        return [
            {
                "event_id": int(row["event_id"]),
                "occurred_at": row["occurred_at"],
                "level": row["level"],
                "component": row["component"],
                "event": row["event"],
                "result": row["result"],
                "correlation_id": row["correlation_id"],
                "parent_correlation_id": row["parent_correlation_id"],
                "details": json_loads(row["details_json"]),
            }
            for row in rows
        ]

    def _append_event(
        self,
        connection: CatalogConnection,
        *,
        occurred_at: str,
        level: str,
        component: str,
        event: str,
        result: str,
        correlation_id: str,
        parent_correlation_id: str | None,
        details: dict[str, Any],
    ) -> int:
        row = connection.execute(
            """
            INSERT INTO operation_events(
                occurred_at, level, component, event, result, correlation_id,
                parent_correlation_id, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING event_id
            """,
            (
                occurred_at, level, component, event, result, correlation_id,
                parent_correlation_id, json_dumps(details),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("operation event insert did not return an identity")
        return int(row["event_id"])

    def _run(self, connection: CatalogConnection, run_id: str) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT job_runs.*, job_occurrences.scheduled_at, job_occurrences.trigger
            FROM job_runs JOIN job_occurrences USING(occurrence_id)
            WHERE job_runs.run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"job run does not exist: {run_id}")
        return _run_payload(row)


def _job_payload(row: CatalogRow) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "task": row["task"],
        "interval_minutes": int(row["interval_minutes"]),
        "enabled": bool(row["enabled"]),
        "version": int(row["version"]),
        "next_run_at": row["next_run_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _run_payload(row: CatalogRow) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "occurrence_id": row["occurrence_id"],
        "attempt": int(row["attempt"]),
        "job_id": row["job_id"],
        "task": row["task"],
        "scheduled_at": row["scheduled_at"],
        "trigger": row["trigger"],
        "worker_id": row["worker_id"],
        "lease_expires_at": row["lease_expires_at"],
        "heartbeat_at": row["heartbeat_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "status": row["status"],
        "summary": row["summary"],
        "details": json_loads(row["details_json"]),
    }


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("operation timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()
