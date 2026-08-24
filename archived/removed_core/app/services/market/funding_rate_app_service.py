from __future__ import annotations

from app.infra.executor import run_database, run_external_io
from app.services.market.funding_rate_service import FundingRateService


class FundingRateAppService:
    def __init__(self, *, funding_rate_service: FundingRateService) -> None:
        self.funding_rate_service = funding_rate_service

    async def get_current_funding_rate(self, symbol: str) -> dict:
        return await run_external_io(lambda: self.funding_rate_service.fetch_current_rate(symbol))

    async def sync_funding_rate_history(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
    ) -> dict:
        return await run_external_io(
            lambda: self.funding_rate_service.sync_history(
                symbol,
                start_date=start_date,
                end_date=end_date,
            )
        )

    async def get_funding_rate_history(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        limit: int | None,
    ) -> dict:
        return await run_database(
            lambda: self.funding_rate_service.get_history(
                symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        )
