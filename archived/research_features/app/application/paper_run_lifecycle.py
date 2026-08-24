from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.infra.executor import run_database
from app.application.backtest.ports import PaperRunWriter
from app.application.run_task_manager import RunTaskManager
from app.contracts.backtest_run import PAPER_LIVE_EXECUTION_MODE, RUN_STATUS_FAILED, update_paper_metadata
from utils.time_utils import utc_now_naive


class PaperRunLifecycle:
    def __init__(
        self,
        *,
        engine: str,
        run_repository,
        paper_runs: PaperRunWriter,
        runtime_state: Callable[[Any], dict[str, Any]],
    ) -> None:
        self.engine = engine
        self.run_repository = run_repository
        self.paper_runs = paper_runs
        self.runtime_state = runtime_state

    def list_active_run_ids(self) -> list[int]:
        return self.run_repository.list_active_run_ids(
            execution_mode=PAPER_LIVE_EXECUTION_MODE,
            engine=self.engine,
        )

    def mark_stopped(self, run_id: int, status: str, reason: str) -> None:
        run = self.paper_runs.get_paper_run(run_id=run_id, engine=self.engine)
        if run is None:
            return
        now = utc_now_naive()
        self.paper_runs.set_paper_status(
            run_id=run_id,
            engine=self.engine,
            status=status,
            metadata=update_paper_metadata(
                run.metadata,
                runtime_state=self.runtime_state(run.metadata),
                last_updated=now.isoformat(),
                stop_reason=reason,
            ),
        )


class PaperRunController:
    def __init__(
        self,
        *,
        engine: str,
        run_repository,
        paper_runs: PaperRunWriter,
        runtime_state: Callable[[Any], dict[str, Any]],
        tick: Callable[[int], bool],
        interval_seconds: Callable[[], float],
        error_label: str,
    ) -> None:
        self.lifecycle = PaperRunLifecycle(
            engine=engine,
            run_repository=run_repository,
            paper_runs=paper_runs,
            runtime_state=runtime_state,
        )
        self._task_manager = RunTaskManager(
            list_active_run_ids=self.lifecycle.list_active_run_ids,
            tick=tick,
            mark_failed=self.mark_failed,
            interval_seconds=interval_seconds,
            error_label=error_label,
        )

    async def start_active_run_monitoring(self) -> None:
        await self._task_manager.start_active_run_monitoring()

    async def shutdown(self) -> None:
        await self._task_manager.shutdown()

    def activate_run(self, run_id: int) -> None:
        self._task_manager.ensure_task(run_id)

    async def cancel_run(self, run_id: int) -> None:
        await self._task_manager.cancel_task(run_id)

    def mark_failed(self, run_id: int, reason: str) -> None:
        self.lifecycle.mark_stopped(run_id, RUN_STATUS_FAILED, reason)

    def mark_stopped(self, run_id: int, status: str, reason: str) -> None:
        self.lifecycle.mark_stopped(run_id, status, reason)


class PaperRunHost:
    def __init__(self, controller: PaperRunController) -> None:
        self._controller = controller

    async def start_active_run_monitoring(self) -> None:
        await self._controller.start_active_run_monitoring()

    async def shutdown(self) -> None:
        await self._controller.shutdown()

    def activate_created_run(self, run_id: int) -> None:
        self._controller.activate_run(run_id)

    async def stop_and_cancel_run(self, run_id: int, *, status: str, reason: str) -> None:
        await run_database(lambda: self._controller.mark_stopped(run_id, status, reason))
        await self._controller.cancel_run(run_id)


class PaperRunHostedService:
    paper_host: PaperRunHost

    async def start_active_run_monitoring(self) -> None:
        await self.paper_host.start_active_run_monitoring()

    async def shutdown(self) -> None:
        await self.paper_host.shutdown()

    def _activate_created_run(self, run_id: int) -> None:
        self.paper_host.activate_created_run(run_id)

    async def _stop_and_cancel_run(self, run_id: int, *, status: str, reason: str) -> None:
        await self.paper_host.stop_and_cancel_run(run_id, status=status, reason=reason)
