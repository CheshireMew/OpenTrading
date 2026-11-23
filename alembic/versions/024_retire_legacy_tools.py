"""Delete data and tables for retired portfolio, report and Python backtest features.

The user explicitly requested removal of historical data on 2026-11-23.
Market history, Pine workspaces and ordinary research notes/price alerts are not targets.
"""
from alembic import op
import sqlalchemy as sa

revision = "024_retire_legacy_tools"
down_revision = "023_kline_archive"
branch_labels = None
depends_on = None

RETIRED_TABLES = (
    "local_backtest_records", "local_backtest_runs", "research_reports",
    "portfolio_ledger_requests", "portfolio_transactions", "portfolio_simulation_results",
    "portfolio_records", "portfolio_collection_state",
)


def upgrade():
    op.execute(sa.text("""
        DELETE FROM research_events
        WHERE entity_type LIKE 'portfolio%' OR entity_type = 'research_report'
           OR (entity_type = 'alert' AND entity_id IN (
               SELECT id FROM research_alert_rules WHERE metric = 'portfolio_drift_pct'
           ))
    """))
    op.execute(sa.text("DELETE FROM research_alert_rules WHERE metric = 'portfolio_drift_pct'"))
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in RETIRED_TABLES:
        if table in existing:
            op.drop_table(table)


def downgrade():
    raise RuntimeError("Retired-feature data was explicitly deleted; this migration cannot restore it")
