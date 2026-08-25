from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from app.contracts.portfolios import PortfolioAnalyticsCommand, PortfolioAnalyticsResponse
from app.domain.portfolio_analytics import analyze_portfolio
from app.infra.executor import run_database
from app.services.market.symbol_catalog import resolve_market_asset
from app.services.tools.portfolio_service import PortfolioService


class PortfolioAnalyticsService:
    def __init__(self, *, portfolio_service: PortfolioService, market_query_service, index_data_service) -> None:
        self._portfolios = portfolio_service
        self._market_query = market_query_service
        self._indexes = index_data_service

    async def analyze(self, portfolio_id: str, command: PortfolioAnalyticsCommand) -> PortfolioAnalyticsResponse:
        ledger = await run_database(lambda: self._portfolios.get_ledger(portfolio_id))
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=command.periodDays)
        symbols = sorted({position.symbol for position in ledger.summary.positions if position.units > 0})
        requested = list(dict.fromkeys([*symbols, command.benchmarkSymbol.upper()]))
        results = await asyncio.gather(
            *(self._load_history(symbol, start, end) for symbol in requested),
            return_exceptions=True,
        )
        histories: dict[str, dict[str, float]] = {}
        issues = list(ledger.summary.issues)
        for symbol, result in zip(requested, results):
            if isinstance(result, Exception):
                issues.append(f"{symbol} 历史价格不可用：{result}")
                histories[symbol] = {}
            else:
                histories[symbol] = result
                if len(result) < 2:
                    issues.append(f"{symbol} 在所选区间内的价格点不足")
        payload = analyze_portfolio(
            portfolio_id=portfolio_id,
            transactions=[item.model_dump() for item in ledger.transactions],
            ledger_summary=ledger.summary.model_dump(),
            price_history={symbol: histories.get(symbol, {}) for symbol in symbols},
            benchmark_symbol=command.benchmarkSymbol.upper(),
            benchmark_history=histories.get(command.benchmarkSymbol.upper(), {}),
            period_days=command.periodDays,
            custom_shocks=command.customShocks,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            issues=issues,
        )
        return PortfolioAnalyticsResponse.model_validate(payload)

    async def _load_history(self, symbol: str, start: date, end: date) -> dict[str, float]:
        resolved = resolve_market_asset(symbol)
        if resolved is None:
            raise ValueError("不在可用市场标的目录中")
        if resolved["asset_class"] == "cash":
            return {(start + timedelta(days=offset)).isoformat(): 1.0 for offset in range((end - start).days + 1)}
        if resolved["asset_class"] == "index":
            response = await self._indexes.get_pricing_history_async(
                symbol=resolved["symbol"],
                timeframe="1d",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
            return {
                datetime.fromtimestamp(item.timestamp / 1000, tz=timezone.utc).date().isoformat(): float(item.close)
                for item in response.data
                if item.close > 0
            }
        response = await self._market_query.get_full_history(
            symbol=resolved["symbol"],
            timeframe="1d",
            start_date=start.isoformat(),
            fetch_policy="hydrate",
        )
        return {
            datetime.fromtimestamp(item.timestamp / 1000, tz=timezone.utc).date().isoformat(): float(item.close)
            for item in response.items
            if item.timestamp
            <= int((datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)).timestamp() * 1000)
            and item.close > 0
        }
