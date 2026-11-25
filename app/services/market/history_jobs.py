from __future__ import annotations


from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
import socket
import logging
from threading import Event, Thread
from typing import Callable
from typing import Literal
from uuid import uuid4

from config.market_data import ConfigurationError, MarketDataConfig
from app.domain.immutability import deep_freeze
from app.services.market.liquidity import sync_liquidity_data
from app.infra.persistence.market.history import MarketHistoryDatabase
from app.infra.persistence.market.history.operations import OperationRepository


JobTask = Literal["liquidity_refresh"]
JobStatus = Literal[
    "pending", "running", "success", "warning", "blocked", "error", "interrupted", "cancelled",
]
JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
JOB_TASKS = {"liquidity_refresh"}
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20.0
LOGGER = logging.getLogger("signal_lab.scheduler")


@dataclass(frozen=True, slots=True)
class JobDefinition:
    job_id: str
    task: JobTask
    interval_minutes: int
    enabled: bool
    version: int
    next_run_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class JobPreset:
    job_id: str
    task: JobTask
    interval_minutes: int


LIQUIDITY_REFRESH_JOB = JobPreset(
    job_id="liquidity-refresh",
    task="liquidity_refresh",
    interval_minutes=240,
)


@dataclass(frozen=True, slots=True)
class JobRun:
    run_id: str
    occurrence_id: str
    attempt: int
    job_id: str
    task: JobTask
    scheduled_at: str
    trigger: Literal["scheduled", "manual"]
    worker_id: str | None
    lease_expires_at: str | None
    heartbeat_at: str | None
    started_at: str
    finished_at: str | None
    status: JobStatus
    summary: str
    details: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", deep_freeze(self.details))


class JobScheduler:
    def __init__(self, config: MarketDataConfig, database: MarketHistoryDatabase) -> None:
        self.config = config
        self.root = database.root
        self._database = database
        self._operations = OperationRepository(self._database)
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex}"

    def add(self, job_id: str, task: str, interval_minutes: int) -> JobDefinition:
        _validate_job_id(job_id)
        if task not in JOB_TASKS:
            raise ValueError("only the liquidity_refresh task is supported")
        if interval_minutes < 1:
            raise ValueError("interval_minutes must be positive")
        payload = self._operations.create_job(
            job_id=job_id,
            task=task,
            interval_minutes=interval_minutes,
            created_at=datetime.now(timezone.utc),
        )
        return JobDefinition(**payload)

    def ensure(self, job_id: str, task: str, interval_minutes: int) -> JobDefinition:
        matching_task = next((item for item in self.jobs() if item.task == task), None)
        if matching_task is not None:
            return matching_task
        return self.add(job_id, task, interval_minutes)

    def ensure_preset(self, preset: JobPreset) -> JobDefinition:
        return self.ensure(preset.job_id, preset.task, preset.interval_minutes)

    def set_enabled(self, job_id: str, enabled: bool) -> JobDefinition:
        return JobDefinition(
            **self._operations.set_enabled(
                job_id,
                enabled,
                changed_at=datetime.now(timezone.utc),
            )
        )

    def jobs(self) -> tuple[JobDefinition, ...]:
        return tuple(JobDefinition(**item) for item in self._operations.jobs())

    def run(self, job_id: str, *, now: datetime | None = None) -> JobRun:
        claimed = self._operations.claim_manual(
            job_id,
            now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc),
            worker_id=self.worker_id,
            lease_seconds=LEASE_SECONDS,
        )
        return self._execute_claim(claimed)

    def due(self, now: datetime | None = None) -> tuple[JobDefinition, ...]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return tuple(JobDefinition(**item) for item in self._operations.due_jobs(now=current))

    def run_due(
        self,
        now: datetime | None = None,
        *,
        stop_event: Event | None = None,
    ) -> tuple[JobRun, ...]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if stop_event is not None and stop_event.is_set():
            return ()
        # Recovery is an execution-side mutation, including when every job has
        # been disabled. Constructing a scheduler or reading status stays read-only.
        self._operations.recover_expired(now=current)
        completed: list[JobRun] = []
        for job in self.due(current):
            if stop_event is not None and stop_event.is_set():
                break
            claimed = self._operations.claim_due(
                job.job_id,
                now=current,
                worker_id=self.worker_id,
                lease_seconds=LEASE_SECONDS,
            )
            if claimed is not None:
                completed.append(self._execute_claim(claimed))
        return tuple(completed)

    def latest(self, job_id: str) -> JobRun | None:
        _validate_job_id(job_id)
        rows = self._operations.runs(job_id=job_id, limit=1)
        return JobRun(**rows[0]) if rows else None

    def history(self, limit: int = 100) -> tuple[JobRun, ...]:
        return tuple(JobRun(**item) for item in self._operations.runs(limit=limit))

    def _execute_claim(self, claimed: dict[str, object]) -> JobRun:
        if claimed["status"] != "running":
            return JobRun(**claimed)  # type: ignore[arg-type]
        definition = JobDefinition(**self._operations.job(str(claimed["job_id"])))
        heartbeat = _LeaseHeartbeat(
            self._operations,
            run_id=str(claimed["run_id"]),
            worker_id=self.worker_id,
        )
        heartbeat.start()
        interruption: BaseException | None = None
        try:
            status, summary, details = self._execute(definition)
        except ConfigurationError as exc:
            status, summary, details = "blocked", str(exc), {}
        except Exception as exc:  # the durable attempt must always acquire a terminal state
            status, summary, details = "error", str(exc), {"error_type": type(exc).__name__}
        except (KeyboardInterrupt, SystemExit) as exc:
            status, summary, details = (
                "interrupted",
                str(exc) or type(exc).__name__,
                {"error_type": type(exc).__name__},
            )
            interruption = exc
        finally:
            heartbeat_stopped = heartbeat.stop(timeout=5.0)
        if not heartbeat_stopped:
            status, summary = "error", "lease heartbeat did not stop within five seconds"
            details = {**details, "heartbeat_shutdown": "timeout"}
        elif heartbeat.error is not None:
            status, summary = "error", f"lease heartbeat failed: {heartbeat.error}"
            details = {
                **details,
                "heartbeat_error_type": type(heartbeat.error).__name__,
            }
        payload = self._operations.complete(
            str(claimed["run_id"]),
            worker_id=self.worker_id,
            status=status,
            summary=summary,
            details=details,
            finished_at=datetime.now(timezone.utc),
        )
        result = JobRun(**payload)
        if interruption is not None:
            raise interruption
        return result

    def _execute(self, job: JobDefinition) -> tuple[JobStatus, str, dict[str, object]]:
        if job.task != "liquidity_refresh":
            raise ValueError(f"unsupported job: {job.task}")
        refreshed = sync_liquidity_data(self._database, self.config)
        return (
            "success",
            f"refreshed {refreshed['series_count']} dollar-liquidity series and "
            f"{refreshed['row_count']} observations",
            {
                "series_count": int(refreshed["series_count"]),
                "row_count": int(refreshed["row_count"]),
                "retrieved_at": str(refreshed["retrieved_at"]),
            },
        )


class JobWatcher:
    """Run persisted interval jobs in one stoppable background worker."""

    def __init__(
        self,
        scheduler: JobScheduler,
        *,
        poll_seconds: float = 30.0,
        on_run: Callable[[JobRun], None] | None = None,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.scheduler = scheduler
        self.poll_seconds = poll_seconds
        self.on_run = on_run
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._watch, name="signal-lab-job-watcher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 5.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=None if timeout is None else max(0.0, timeout))
            if thread.is_alive():
                return False
        self._thread = None
        return True

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                for result in self.scheduler.run_due(stop_event=self._stop):
                    if self.on_run is not None:
                        try:
                            self.on_run(result)
                        except Exception:
                            LOGGER.exception("scheduled job completion callback failed")
                    if self._stop.is_set():
                        break
            except Exception:
                LOGGER.exception("scheduled job watcher iteration failed")
            self._stop.wait(self.poll_seconds)


def _validate_job_id(job_id: str) -> None:
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("job_id must contain only letters, numbers, dot, underscore, and hyphen")


class _LeaseHeartbeat:
    def __init__(self, repository: OperationRepository, *, run_id: str, worker_id: str) -> None:
        self._repository = repository
        self.run_id = run_id
        self.worker_id = worker_id
        self._stop = Event()
        self.error: Exception | None = None
        self._thread = Thread(
            target=self._run,
            name=f"signal-lab-heartbeat-{run_id[-8:]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> bool:
        self._stop.set()
        self._thread.join(max(0.0, timeout))
        return not self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                active = self._repository.heartbeat(
                    self.run_id,
                    worker_id=self.worker_id,
                    now=datetime.now(timezone.utc),
                    lease_seconds=LEASE_SECONDS,
                )
            except Exception as exc:
                self.error = exc
                LOGGER.exception("lease heartbeat failed for %s", self.run_id)
                if self._stop.wait(min(HEARTBEAT_SECONDS, 1.0)):
                    return
                continue
            if not active:
                self.error = RuntimeError("job lease is no longer active")
                return
