from __future__ import annotations

import asyncio
import signal

from app.background_runtime import BackgroundRuntimeStatus
from app.main import create_app
from utils.logger import logger


async def main() -> None:
    app = create_app(role="background")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signal_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda _sig, _frame: request_stop())

    async with app.router.lifespan_context(app):
        background_services_task = getattr(app.state, "background_services_task", None)
        if background_services_task is None:
            raise RuntimeError("Background services task was not created.")
        await background_services_task

        background_runtime = getattr(app.state, "background_runtime", None)
        if background_runtime is None:
            raise RuntimeError("Background runtime was not created.")
        await background_runtime.wait_until_started()
        state = background_runtime.state
        if state.status != BackgroundRuntimeStatus.READY:
            if state.error is not None:
                raise state.error
            raise RuntimeError(f"Background runtime did not become ready: {state.status}")

        logger.info("Heimdall background runtime started.")
        await stop_event.wait()
        logger.info("Heimdall background runtime stopping.")


if __name__ == "__main__":
    asyncio.run(main())
