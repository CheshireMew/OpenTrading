"""Removal includes data, while market history and regular price alerts survive."""
from datetime import datetime

import pytest
import sqlalchemy as sa
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts.research import ResearchAlertCreateCommand
from app.infra.db import build_database_runtime
from app.infra.db.schema_runtime import _alembic_config, verify_database_schema
from app.main import create_app
from config.settings import AppSettings
from scripts.research_cli import build_parser

RETIRED = {
    'local_backtest_records', 'local_backtest_runs', 'research_reports', 'portfolio_ledger_requests',
    'portfolio_transactions', 'portfolio_simulation_results', 'portfolio_records', 'portfolio_collection_state',
}


def test_portfolio_and_report_routes_and_cli_are_closed():
    app = create_app('api')
    paths = app.openapi()['paths']
    prefixes = ('/api/v1/tools/portfolios', '/api/v1/research/reports')
    assert not any(path.startswith(prefixes) for path in paths)
    assert '/api/v1/chart-workspace/pine-runs' in paths
    assert '/api/v1/tools/dca_simulate' in paths
    assert '/api/v1/tools/compare_pairs' in paths
    client = TestClient(app)
    for path in prefixes:
        assert client.get(path).status_code == 404
    for resource in ('portfolio', 'report'):
        with pytest.raises(SystemExit):
            build_parser().parse_args([resource])
    with pytest.raises(ValidationError, match='组合平衡已退出'):
        ResearchAlertCreateCommand(symbol='BTC/USDT', name='retired', metric='portfolio_drift_pct',
                                   operator='gt', threshold=5)


def test_retirement_migration_deletes_only_retired_data(tmp_path):
    runtime = build_database_runtime(AppSettings(DATABASE_URL=f'sqlite:///{(tmp_path / "legacy.db").as_posix()}'))
    config = _alembic_config(runtime.database_url)
    try:
        command.upgrade(config, '023_kline_archive')
        metadata = sa.MetaData()
        metadata.reflect(bind=runtime.engine)
        with runtime.engine.begin() as connection:
            # Every retired table contains data, including child rows. Supply
            # required reflected columns without importing the archived runtime.
            for name in ('portfolio_records', 'portfolio_transactions', 'portfolio_simulation_results',
                         'portfolio_ledger_requests', 'local_backtest_runs', 'local_backtest_records', 'research_reports'):
                table = metadata.tables[name]
                values = {}
                for col in table.columns:
                    if col.nullable or col.server_default is not None:
                        continue
                    if isinstance(col.type, sa.JSON):
                        value = {}
                    elif isinstance(col.type, sa.DateTime):
                        value = datetime(2026, 1, 1)
                    elif isinstance(col.type, sa.Boolean):
                        value = True
                    elif isinstance(col.type, (sa.Integer, sa.Float)):
                        value = 1
                    else:
                        value = 'retired'
                    values[col.name] = value
                values.update({k: v for k, v in {'id': 'retired', 'portfolio_id': 'retired',
                               'run_id': 'retired', 'transaction_type': 'deposit'}.items() if k in table.c})
                connection.execute(table.insert().values(**values))
            connection.execute(sa.text("INSERT INTO klines(symbol,timeframe,timestamp,open,high,low,close,volume,finalized) VALUES ('BTC/USDT','1h',1704067200000,1,2,0.5,1.5,7,1)"))
            alerts = metadata.tables['research_alert_rules']
            for alert_id, metric in [('drift', 'portfolio_drift_pct'), ('price', 'price')]:
                connection.execute(alerts.insert().values(
                    id=alert_id, symbol='BTC/USDT', name=alert_id, metric=metric, operator='gt', threshold=5,
                    enabled=True, cooldown_minutes=60, notification_channels=[], configuration={}, version=1,
                    created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1)))
            events = metadata.tables['research_events']
            for key, kind, entity_id in [('report-event', 'research_report', 'retired'),
                                         ('portfolio-event', 'portfolio_collection', 'retired'),
                                         ('drift-event', 'alert', 'drift'), ('price-event', 'alert', 'price')]:
                connection.execute(events.insert().values(id=key, entity_type=kind, entity_id=entity_id,
                    kind='created', title=key, body='', payload={}, occurred_at=datetime(2026, 1, 1),
                    created_at=datetime(2026, 1, 1)))
        command.upgrade(config, 'head')
        assert not RETIRED & set(sa.inspect(runtime.engine).get_table_names())
        with runtime.engine.connect() as connection:
            assert connection.execute(sa.text('SELECT id FROM research_alert_rules')).scalars().all() == ['price']
            assert connection.execute(sa.text('SELECT id FROM research_events')).scalars().all() == ['price-event']
            assert connection.execute(sa.text('SELECT close,volume FROM klines')).one() == (1.5, 7)
        verify_database_schema(runtime)
    finally:
        runtime.dispose()
