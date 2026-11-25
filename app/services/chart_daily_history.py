"""Expose the existing cross-asset daily history to the chart workspace."""
from __future__ import annotations

import asyncio
from datetime import date

from app.contracts.chart_workspace import ChartSymbol
from app.domain.market.history.catalog_seed import seed_records
from app.infra.executor import run_external_io


def daily_chart_symbols() -> list[ChartSymbol]:
    symbols = []
    for record in seed_records():
        instrument = record.instrument
        if instrument.asset_class not in {"fx", "commodity"}:
            continue
        symbols.append(ChartSymbol(
            id=f"{instrument.asset_class}:{instrument.exchange.lower()}:{instrument.canonical_code}",
            symbol=instrument.canonical_code,
            name=instrument.name,
            exchange=instrument.exchange,
            market=instrument.asset_class,
            currency=instrument.currency,
            timeframes=["1d"],
            timezone=instrument.timezone,
            session="regular",
            aliases=sorted({alias for alias, _ in record.aliases} | set(record.provider_mappings.values())),
            metadata={"price_basis": "raw", "is_continuous": instrument.is_continuous},
        ))
    return symbols


class ChartDailyHistory:
    def __init__(self, market_data) -> None:
        self.runtime = market_data
        self.requests: dict[tuple[str, date, date], asyncio.Task] = {}

    async def snapshot(self, symbol: str, start: date, end: date):
        identity = (symbol, start, end)
        task = self.requests.get(identity)
        if task is None:
            def load():
                return self.runtime.prices.daily_snapshot(symbol, start=start, end=end)
            task = asyncio.create_task(run_external_io(load))
            self.requests[identity] = task
            def finished(completed):
                self.requests.pop(identity, None)
                if not completed.cancelled():
                    completed.exception()
            task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def close(self):
        # An in-flight blocking fetch owns its snapshot write until it finishes.
        await asyncio.gather(*self.requests.values(), return_exceptions=True)
