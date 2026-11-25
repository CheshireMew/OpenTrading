from __future__ import annotations

from sqlalchemy import func, select, text

from app.infra.db.database import DatabaseRuntime
from app.domain.market.indicator_catalog import MARKET_INDICATOR_META
from app.infra.db.schema import BinanceMarketResearchSeries, MarketIndicatorData, ResearchAlertRule, ResearchNote, ResearchWatchItem, RuntimeComponentStatus, TradeSignalRecord
from app.infra.persistence.market.kline_archive import KlineArchive


class DataHealthRepository:
    def __init__(self, database_runtime: DatabaseRuntime) -> None:
        self._database_runtime = database_runtime

    def snapshot(self) -> dict:
        with self._database_runtime.session_scope() as session:
            # Keep hot aggregates and immutable archive references on the same
            # read snapshot while an archival transaction moves rows between tiers.
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN"))
            elif session.get_bind().dialect.name == "postgresql":
                session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            klines = KlineArchive(self._database_runtime).coverage_summary(session)
            indicators = [
                {"indicatorId": row[0], "count": int(row[1]), "first": row[2], "last": row[3]}
                for row in session.execute(
                    select(
                        MarketIndicatorData.indicator_id,
                        func.count(),
                        func.min(MarketIndicatorData.timestamp),
                        func.max(MarketIndicatorData.timestamp),
                    ).where(MarketIndicatorData.indicator_id.in_(MARKET_INDICATOR_META))
                    .group_by(MarketIndicatorData.indicator_id)
                )
            ]
            research_series = [
                {
                    "market": row[0],
                    "series": row[1],
                    "symbol": row[2],
                    "period": row[3],
                    "contractType": row[4],
                    "count": int(row[5]),
                    "first": row[6],
                    "last": row[7],
                }
                for row in session.execute(
                    select(
                        BinanceMarketResearchSeries.market,
                        BinanceMarketResearchSeries.series,
                        BinanceMarketResearchSeries.symbol,
                        BinanceMarketResearchSeries.period,
                        BinanceMarketResearchSeries.contract_type,
                        func.count(),
                        func.min(BinanceMarketResearchSeries.timestamp),
                        func.max(BinanceMarketResearchSeries.timestamp),
                    ).group_by(
                        BinanceMarketResearchSeries.market,
                        BinanceMarketResearchSeries.series,
                        BinanceMarketResearchSeries.symbol,
                        BinanceMarketResearchSeries.period,
                        BinanceMarketResearchSeries.contract_type,
                    )
                )
            ]
            runtime = [
                {
                    "component": row.component,
                    "status": row.status,
                    "heartbeatAt": row.heartbeat_at,
                    "lastSuccessAt": row.last_success_at,
                    "lastFailureAt": row.last_failure_at,
                    "nextRunAt": row.next_run_at,
                    "errorCode": row.error_code,
                    "errorDetail": row.error_detail,
                }
                for row in session.scalars(select(RuntimeComponentStatus).order_by(RuntimeComponentStatus.component))
            ]
            counts = {
                "watchItems": int(session.scalar(select(func.count()).select_from(ResearchWatchItem)) or 0),
                "notes": int(session.scalar(select(func.count()).select_from(ResearchNote)) or 0),
                "alerts": int(session.scalar(select(func.count()).select_from(ResearchAlertRule)) or 0),
                "signals": int(session.scalar(select(func.count()).select_from(TradeSignalRecord)) or 0),
            }
            revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            return {
                "klines": klines,
                "indicators": indicators,
                "researchSeries": research_series,
                "runtime": runtime,
                "counts": counts,
                "databaseRevision": revision,
            }
