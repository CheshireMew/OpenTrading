from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.contracts.data_health import DataHealthResponse, DataRepairCommand
from app.contracts.research import ResearchArchiveCommand, ResearchReportGenerateCommand
from app.infra.persistence.data_health_repository import DataHealthRepository
from app.infra.persistence.research_report_repository import ResearchReportRepository
from app.infra.persistence.research_repository import ResearchRepository
from app.infra.persistence.trade_signal_repository import TradeSignalRepository
from app.infra.persistence.market.kline_store import KlineStore
from app.infra.db.schema import PortfolioRecord
from app.services.data_health_service import DataHealthService
from app.services.research_report_service import ResearchReportService


class StubSnapshot:
    def health_snapshot(self):
        return {"status": "ready", "seedSuccessCount": 3, "activeStreams": 3, "error": None}

    async def get_market_page_snapshot_data(self):
        return {
            "updated_at": int(datetime.now(timezone.utc).timestamp() * 1000),
            "spot_ticker": {"items": [{}]},
            "usdm_ticker": {"items": [{}]},
            "usdm_mark": {"items": [{}]},
        }


@pytest.mark.asyncio
async def test_data_health_reports_coverage_and_scoped_database_repair(installed_database_runtime):
    verified = []
    KlineStore(database_runtime=installed_database_runtime).save(
        "BTC/USDT",
        "1h",
        [
            [1_700_000_000_000, 1, 1, 1, 1, 1],
            [1_700_007_200_000, 1, 1, 1, 1, 1],
        ],
    )
    service = DataHealthService(
        repository=DataHealthRepository(installed_database_runtime),
        database_verifier=lambda: verified.append(True),
        market_query_service=object(),
        index_data_service=object(),
        binance_market_service=SimpleNamespace(snapshot_service=StubSnapshot()),
        research_alert_runtime=object(),
        trade_signal_runtime=object(),
        cache_service=SimpleNamespace(
            runtime_backend="memory_fallback",
            local_entry_count=3,
            local_byte_size=256,
        ),
    )

    health = await service.get_health()
    repair = await service.repair(DataRepairCommand(action="verify_database"))

    assert health.databaseRevision == "018_local_backtests"
    assert any(source.id == "database" for source in health.sources)
    kline_source = next(source for source in health.sources if source.id == "klines")
    assert kline_source.gapCount == 1
    assert kline_source.coverageStart is not None
    assert next(source for source in health.sources if source.id == "runtime_cache").metadata["backend"] == "memory_fallback"
    assert repair.status == "completed"
    assert verified == [True]


class StubHealth:
    async def get_health(self):
        return DataHealthResponse(
            status="healthy",
            checkedAt=datetime.now(timezone.utc),
            databaseRevision="017_research_reports",
            sources=[],
            summary={"problemSourceCount": 0},
        )


@pytest.mark.asyncio
async def test_research_report_keeps_markdown_and_structured_snapshot(installed_database_runtime):
    service = ResearchReportService(
        repository=ResearchReportRepository(installed_database_runtime),
        research_repository=ResearchRepository(installed_database_runtime),
        signal_repository=TradeSignalRepository(installed_database_runtime),
        portfolio_service=object(),
        data_health_service=StubHealth(),
        asset_research_service=object(),
    )
    report = await service.generate(ResearchReportGenerateCommand(title="Daily Brief", reportType="daily_brief"))

    assert report.contentMarkdown.startswith("# Daily Brief")
    assert report.dataSnapshot["dataHealth"]["status"] == "healthy"
    assert "数据质量" in report.contentMarkdown
    assert "本期研究清单变更" in report.contentMarkdown
    assert "本期已触发提醒" in report.contentMarkdown
    assert "置信度校准" in report.contentMarkdown
    page = service.list_reports(include_archived=False, offset=0, limit=20)
    assert page.total == 1

    archived = service.archive(
        report.id,
        ResearchArchiveCommand(expectedVersion=report.version),
        archived=True,
    )
    assert archived.archivedAt is not None


class _PayloadModel:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, **_kwargs):
        return self.payload


class _PortfolioService:
    def get_ledger(self, portfolio_id):
        return _PayloadModel({
            "portfolioId": portfolio_id,
            "summary": {
                "totalEquity": 100_000,
                "totalPnl": 5_000,
                "simpleReturnPct": 5,
                "moneyWeightedReturnPct": 4.5,
                "realizedPnl": 2_000,
                "unrealizedPnl": 3_000,
                "totalFees": 50,
            },
        })


class _PortfolioAnalytics:
    async def analyze(self, portfolio_id, command):
        return _PayloadModel({
            "portfolioId": portfolio_id,
            "timeWeightedReturnPct": 6,
            "moneyWeightedReturnPct": 4.5,
            "benchmarkReturnPct": 3,
            "excessReturnPct": 3,
            "annualizedVolatilityPct": 20,
            "maxDrawdownPct": 12,
            "valueAtRisk95": 2_500,
            "concentrationHhi": 0.5,
            "topPositionWeightPct": 60,
            "effectivePositionCount": 2,
            "scenarios": [{"name": "Market -25%", "projectedPnl": -25_000, "projectedReturnPct": -25, "projectedEquity": 75_000}],
            "issues": [],
        })


@pytest.mark.asyncio
async def test_weekly_report_includes_portfolio_risk_and_period_sections(installed_database_runtime):
    portfolio_id = "portfolio-1"
    with installed_database_runtime.session_scope() as session:
        session.add(PortfolioRecord(id=portfolio_id, payload={}))
    service = ResearchReportService(
        repository=ResearchReportRepository(installed_database_runtime),
        research_repository=ResearchRepository(installed_database_runtime),
        signal_repository=TradeSignalRepository(installed_database_runtime),
        portfolio_service=_PortfolioService(),
        portfolio_analytics_service=_PortfolioAnalytics(),
        data_health_service=StubHealth(),
        asset_research_service=object(),
    )

    report = await service.generate(
        ResearchReportGenerateCommand(
            title="Weekly Brief",
            reportType="weekly_brief",
            portfolioId=portfolio_id,
        )
    )

    assert report.dataSnapshot["period"]["days"] == 7
    assert report.dataSnapshot["portfolioAnalytics"] is not None, report.dataSnapshot["generationIssues"]
    assert report.dataSnapshot["portfolioAnalytics"]["excessReturnPct"] == 3
    assert "组合收益与风险" in report.contentMarkdown
    assert "压力情景" in report.contentMarkdown
