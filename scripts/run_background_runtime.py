from __future__ import annotations

import asyncio
import argparse
import signal

from app.background_runtime import BackgroundRuntimeStatus
from app.main import create_app
from utils.logger import logger


async def main(*, report_ready: bool = False) -> None:
    app = create_app(role="background")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
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

        if report_ready:
            print("OPENTRADING_BACKGROUND_READY", flush=True)
        logger.info("OpenTrading background runtime started.")
        await stop_event.wait()
        logger.info("OpenTrading background runtime stopping.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenTrading background runtime")
    parser.add_argument("--report-ready", action="store_true", help=argparse.SUPPRESS)
    asyncio.run(main(report_ready=parser.parse_args().report_ready))
