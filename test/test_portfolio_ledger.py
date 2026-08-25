from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.contracts.portfolios import (
    PortfolioBalanceAsset,
    PortfolioBalancePortfolio,
    PortfolioBalanceSimulation,
    PortfolioBalanceSnapshot,
    PortfolioBalanceStrategy,
    PortfolioBalanceTracking,
    PortfolioCollectionSaveCommand,
    PortfolioTransactionArchiveCommand,
    PortfolioTransactionCreateCommand,
    PortfolioTransactionImportCommand,
)
from app.infra.persistence.portfolio_repository import PortfolioRepository
from app.services.tools.portfolio_service import PortfolioService
from app.domain.portfolio_analytics import analyze_portfolio


@pytest.fixture
def ledger_service(installed_database_runtime):
    service = PortfolioService(PortfolioRepository(installed_database_runtime))
    now = datetime.now(timezone.utc).isoformat()
    service.save_collection(
        PortfolioCollectionSaveCommand(
            expectedRevision=0,
            snapshot=PortfolioBalanceSnapshot(
                activePortfolioId="core",
                portfolios=[
                    PortfolioBalancePortfolio(
                        id="core",
                        name="Core",
                        assets=[
                            PortfolioBalanceAsset(
                                id="btc",
                                symbol="BTC",
                                targetWeight=100,
                                units=0.75,
                                currentPrice=10_000,
                                seedValue=0,
                            )
                        ],
                        strategy=PortfolioBalanceStrategy(),
                        tracking=PortfolioBalanceTracking(
                            virtualCapital=10_000,
                            inceptionDate="2026-01-01",
                        ),
                        simulation=PortfolioBalanceSimulation(
                            initialCapital=10_000,
                            simulationStartDate="2026-01-01",
                        ),
                        createdAt=now,
                        updatedAt=now,
                    )
                ],
            ),
        )
    )
    return service


def _transaction(kind: str, **updates) -> PortfolioTransactionCreateCommand:
    payload = {
        "transactionType": kind,
        "symbol": "",
        "quantity": 0,
        "unitPrice": 0,
        "cashAmount": 0,
        "fee": 0,
        "currency": "USD",
        "feeCurrency": "USD",
        "occurredAt": "2026-01-01T00:00:00Z",
    }
    payload.update(updates)
    return PortfolioTransactionCreateCommand.model_validate(payload)


def test_portfolio_ledger_derives_cost_cash_and_profit(ledger_service):
    ledger_service.create_transaction(
        "core",
        _transaction("deposit", cashAmount=10_000, externalId="deposit-1"),
    )
    purchase = ledger_service.create_transaction(
        "core",
        _transaction(
            "buy",
            symbol="btc",
            quantity=1,
            unitPrice=5_000,
            fee=10,
            externalId="buy-1",
            occurredAt="2026-01-02T00:00:00Z",
        ),
    )
    ledger_service.create_transaction(
        "core",
        _transaction(
            "sell",
            symbol="BTC",
            quantity=0.25,
            unitPrice=8_000,
            fee=5,
            occurredAt="2026-01-03T00:00:00Z",
        ),
    )

    ledger = ledger_service.get_ledger("core")
    assert len(ledger.transactions) == 3
    assert ledger.summary.cashBalance == pytest.approx(6_985)
    assert ledger.summary.totalFees == pytest.approx(15)
    assert ledger.summary.marketValue == pytest.approx(7_500)
    assert ledger.summary.realizedPnl == pytest.approx(742.5)
    assert ledger.summary.unrealizedPnl == pytest.approx(3_742.5)
    assert ledger.summary.totalPnl == pytest.approx(4_485)
    assert ledger.summary.simpleReturnPct == pytest.approx(44.85)
    assert ledger.summary.moneyWeightedReturnPct is not None
    assert ledger.summary.positions[0].averageCost == pytest.approx(5_010)

    archived = ledger_service.archive_transaction(
        "core",
        purchase.id,
        PortfolioTransactionArchiveCommand(expectedVersion=purchase.version),
        archived=True,
    )
    assert archived.archivedAt is not None
    archived_ledger = ledger_service.get_ledger("core")
    assert len(archived_ledger.archivedTransactions) == 1
    assert archived_ledger.summary.reliability == "incomplete"


def test_portfolio_analytics_calculates_twr_risk_and_scenarios():
    transactions = [
        {
            "id": "deposit",
            "transactionType": "deposit",
            "symbol": "",
            "quantity": 0,
            "unitPrice": 0,
            "cashAmount": 1_000,
            "fee": 0,
            "occurredAt": datetime(2026, 1, 1),
        },
        {
            "id": "buy",
            "transactionType": "buy",
            "symbol": "BTC/USDT",
            "quantity": 10,
            "unitPrice": 100,
            "cashAmount": 0,
            "fee": 0,
            "occurredAt": datetime(2026, 1, 1),
        },
    ]
    history = {
        "BTC/USDT": {
            "2026-01-01": 100,
            "2026-01-02": 110,
            "2026-01-03": 105,
            "2026-01-04": 120,
        }
    }
    result = analyze_portfolio(
        portfolio_id="core",
        transactions=transactions,
        ledger_summary={
            "totalEquity": 1_200,
            "moneyWeightedReturnPct": 20,
            "positions": [{"symbol": "BTC/USDT", "marketValue": 1_200}],
        },
        price_history=history,
        benchmark_symbol="BTC/USDT",
        benchmark_history=history["BTC/USDT"],
        period_days=30,
        custom_shocks={"BTC/USDT": -50},
        start_date="2026-01-01",
        end_date="2026-01-04",
        issues=[],
    )
    assert result["timeWeightedReturnPct"] == pytest.approx(20)
    assert result["benchmarkReturnPct"] == pytest.approx(20)
    assert result["topPositionWeightPct"] == pytest.approx(100)
    assert result["assets"][0]["riskContributionPct"] == pytest.approx(100)
    custom = next(item for item in result["scenarios"] if item["id"] == "custom")
    assert custom["projectedPnl"] == pytest.approx(-600)


def test_portfolio_ledger_replace_import_keeps_old_rows_recoverable(ledger_service):
    original = ledger_service.create_transaction(
        "core",
        _transaction("deposit", cashAmount=1_000, externalId="cash-1"),
    )
    imported = ledger_service.import_transactions(
        "core",
        PortfolioTransactionImportCommand(
            mode="replace",
            transactions=[
                _transaction("deposit", cashAmount=2_000, externalId="cash-1"),
                _transaction(
                    "buy",
                    symbol="BTC",
                    quantity=0.1,
                    unitPrice=10_000,
                    occurredAt="2026-01-02T00:00:00Z",
                ),
            ],
        ),
    )
    assert imported.importedCount == 2
    assert imported.archivedCount == 1
    assert len(imported.ledger.transactions) == 2
    assert imported.ledger.archivedTransactions[0].id == original.id
