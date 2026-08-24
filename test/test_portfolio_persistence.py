from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest

from app.contracts.portfolios import (
    LegacyPortfolioBalancePortfolio,
    LegacyPortfolioBalanceSnapshot,
    LegacyPortfolioExportDocument,
    PortfolioBalanceAsset,
    PortfolioBalancePortfolio,
    PortfolioBalanceSimulation,
    PortfolioBalanceSnapshot,
    PortfolioBalanceStrategy,
    PortfolioBalanceTracking,
    PortfolioCollectionImportCommand,
    PortfolioCollectionChangeCommand,
    PortfolioCollectionSaveCommand,
    PortfolioExportDocument,
    PortfolioSimulationEquityPoint,
    PortfolioSimulationResultCommand,
    PortfolioSimulationSummary,
)
from app.domain.portfolios import PortfolioRevisionConflictError
from app.infra.db.database import DatabaseRuntime
from app.infra.persistence.portfolio_repository import PortfolioRepository
from app.services.tools.portfolio_service import PortfolioService


def _portfolio(portfolio_id: str = "core", name: str = "Core") -> PortfolioBalancePortfolio:
    now = datetime.now(timezone.utc).isoformat()
    return PortfolioBalancePortfolio(
        id=portfolio_id,
        name=name,
        assets=[
            PortfolioBalanceAsset(
                id="btc",
                symbol="BTC",
                targetWeight=100,
                units=1,
                currentPrice=60_000,
                seedValue=60_000,
            )
        ],
        strategy=PortfolioBalanceStrategy(
            rebalanceBand=5,
            minTradeAmount=10,
            reviewFrequency="monthly",
        ),
        tracking=PortfolioBalanceTracking(
            virtualCapital=60_000,
            inceptionDate="2026-01-01",
        ),
        simulation=PortfolioBalanceSimulation(
            initialCapital=60_000,
            simulationStartDate="2026-01-01",
        ),
        createdAt=now,
        updatedAt=now,
    )


def _simulation(point_count: int = 2) -> PortfolioSimulationSummary:
    return PortfolioSimulationSummary(
        startDate="2026-01-01",
        endDate="2026-01-02",
        initialValue=60_000,
        finalValue=61_000,
        totalReturnPct=1.67,
        annualizedReturnPct=10.0,
        maxDrawdownPct=0,
        reviewCount=1,
        outOfBandReviewCount=0,
        rebalanceCount=0,
        equityCurve=[
            PortfolioSimulationEquityPoint(
                id=index,
                timestamp=f"2026-01-01T00:00:{index % 60:02d}",
                equity=60_000 + index,
                pnl_abs=index,
                drawdown_pct=0,
            )
            for index in range(point_count)
        ],
    )


@pytest.fixture
def portfolio_service(tmp_path):
    runtime = DatabaseRuntime(
        database_url=f"sqlite:///{(tmp_path / 'portfolio.db').as_posix()}",
        source="test",
    )
    from app.infra.db.schema import Base

    Base.metadata.create_all(runtime.engine)
    service = PortfolioService(PortfolioRepository(runtime))
    yield service, runtime
    runtime.dispose()


def test_portfolio_collection_survives_service_recreation(portfolio_service):
    service, runtime = portfolio_service
    saved = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio()],
            ),
        )
    )
    assert saved.revision == 1

    reloaded = PortfolioService(PortfolioRepository(runtime)).get_collection()
    assert reloaded.revision == 1
    assert reloaded.snapshot.activePortfolioId == "core"
    assert reloaded.snapshot.portfolios[0].name == "Core"


def test_portfolio_collection_rejects_stale_revision(portfolio_service):
    service, _runtime = portfolio_service
    command = PortfolioCollectionSaveCommand(
        expectedRevision=0,
        snapshot=PortfolioBalanceSnapshot(
            activePortfolioId="core",
            portfolios=[_portfolio()],
        ),
    )
    service.save_collection(command)

    with pytest.raises(PortfolioRevisionConflictError, match="组合已在其它窗口更新"):
        service.save_collection(command)


def test_change_set_only_replaces_changed_portfolios(portfolio_service):
    service, _runtime = portfolio_service
    first = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio(), _portfolio("satellite", "Satellite")],
            ),
        )
    )
    changed = _portfolio("core", "Core updated")

    response = service.apply_collection_changes(
        PortfolioCollectionChangeCommand(
            expectedRevision=first.revision,
            activePortfolioId="core",
            changedPortfolios=[changed],
            portfolioOrder=["satellite", "core"],
        )
    )

    assert response.revision == first.revision + 1
    assert [item.id for item in response.snapshot.portfolios] == ["satellite", "core"]
    assert response.snapshot.portfolios[0].name == "Satellite"
    assert response.snapshot.portfolios[1].name == "Core updated"


def test_sqlite_revision_claim_allows_exactly_one_concurrent_writer(portfolio_service):
    service, _runtime = portfolio_service
    first = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio()],
            ),
        )
    )
    start = Barrier(2)

    def save(name: str):
        start.wait()
        return service.apply_collection_changes(
            PortfolioCollectionChangeCommand(
                expectedRevision=first.revision,
                activePortfolioId="core",
                changedPortfolios=[_portfolio("core", name)],
                portfolioOrder=["core"],
            )
        )

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(save, "Writer A"), executor.submit(save, "Writer B")]
        for future in futures:
            try:
                outcomes.append(("saved", future.result()))
            except PortfolioRevisionConflictError as error:
                outcomes.append(("conflict", error))

    assert [kind for kind, _result in outcomes].count("saved") == 1
    assert [kind for kind, _result in outcomes].count("conflict") == 1


def test_removed_portfolio_is_soft_deleted_and_restorable(portfolio_service):
    service, _runtime = portfolio_service
    first = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio(), _portfolio("satellite", "Satellite")],
            ),
        )
    )
    second = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=first.revision,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio()],
            ),
        )
    )

    deleted = service.list_deleted(offset=0, limit=20)
    assert [item.id for item in deleted.items] == ["satellite"]
    assert deleted.total == 1
    restored = service.restore_portfolio("satellite", second.revision)
    assert restored.revision == second.revision + 1
    assert {item.id for item in restored.snapshot.portfolios} == {"core", "satellite"}


def test_replace_import_soft_deletes_missing_records(portfolio_service):
    service, _runtime = portfolio_service
    current = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio(), _portfolio("satellite", "Satellite")],
            ),
        )
    )
    document = PortfolioExportDocument(
        schemaVersion=2,
        exportedAt=datetime.now(timezone.utc),
        snapshot=PortfolioBalanceSnapshot(
            activePortfolioId="imported",
            portfolios=[_portfolio("imported", "Imported")],
        ),
        deletedPortfolios=[],
    )
    imported = service.import_collection(
        PortfolioCollectionImportCommand(
            expectedRevision=current.revision,
            mode="replace",
            document=document,
        )
    )

    assert [item.id for item in imported.snapshot.portfolios] == ["imported"]
    deleted = service.list_deleted(offset=0, limit=20)
    assert {item.id for item in deleted.items} == {"core", "satellite"}


def test_simulation_result_is_separate_and_invalidated_by_input_change(portfolio_service):
    service, _runtime = portfolio_service
    saved = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio()],
            ),
        )
    )
    service.save_simulation(
        "core",
        PortfolioSimulationResultCommand(
            expectedRevision=saved.revision,
            result=_simulation(),
        ),
    )

    collection = service.get_collection()
    assert "lastSimulationResult" not in collection.model_dump_json()
    assert service.get_simulation("core").result is not None

    renamed = _portfolio(name="Renamed")
    renamed_response = service.apply_collection_changes(
        PortfolioCollectionChangeCommand(
            expectedRevision=saved.revision,
            activePortfolioId="core",
            changedPortfolios=[renamed],
            portfolioOrder=["core"],
        )
    )
    assert service.get_simulation("core").result is not None

    changed_input = _portfolio(name="Renamed")
    changed_input.assets[0].targetWeight = 90
    service.apply_collection_changes(
        PortfolioCollectionChangeCommand(
            expectedRevision=renamed_response.revision,
            activePortfolioId="core",
            changedPortfolios=[changed_input],
            portfolioOrder=["core"],
        )
    )
    assert service.get_simulation("core").result is None


def test_large_simulation_does_not_expand_collection_response(portfolio_service):
    service, _runtime = portfolio_service
    saved = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio()],
            ),
        )
    )
    service.save_simulation(
        "core",
        PortfolioSimulationResultCommand(
            expectedRevision=saved.revision,
            result=_simulation(5_000),
        ),
    )

    assert len(service.get_collection().model_dump_json()) < 10_000
    assert len(service.get_simulation("core").result.equityCurve) == 5_000


def test_export_v2_and_legacy_v1_import_preserve_simulation(portfolio_service):
    service, _runtime = portfolio_service
    saved = service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[_portfolio()],
            ),
        )
    )
    service.save_simulation(
        "core",
        PortfolioSimulationResultCommand(
            expectedRevision=saved.revision,
            result=_simulation(),
        ),
    )
    exported = service.export_collection()
    assert exported.schemaVersion == 2
    assert exported.simulationResults[0].portfolioId == "core"

    legacy_portfolio = LegacyPortfolioBalancePortfolio.model_validate(
        {
            **_portfolio("legacy", "Legacy").model_dump(mode="json"),
            "lastSimulationResult": _simulation().model_dump(mode="json"),
        }
    )
    legacy = LegacyPortfolioExportDocument(
        schemaVersion=1,
        exportedAt=datetime.now(timezone.utc),
        snapshot=LegacyPortfolioBalanceSnapshot(
            activePortfolioId="legacy",
            portfolios=[legacy_portfolio],
        ),
    )
    imported = service.import_collection(
        PortfolioCollectionImportCommand(
            expectedRevision=saved.revision,
            mode="replace",
            document=legacy,
        )
    )
    assert imported.snapshot.activePortfolioId == "legacy"
    assert service.get_simulation("legacy").result is not None
