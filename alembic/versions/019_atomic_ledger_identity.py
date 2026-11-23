"""Enforce one active ledger transaction per external identity."""
from alembic import op
import sqlalchemy as sa

revision = "019_atomic_ledger_identity"
down_revision = "018_local_backtests"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    duplicates = connection.execute(sa.text("""
        SELECT portfolio_id, external_id, COUNT(*) AS count
        FROM portfolio_transactions
        WHERE archived_at IS NULL AND external_id IS NOT NULL AND external_id <> ''
        GROUP BY portfolio_id, external_id HAVING COUNT(*) > 1
    """)).fetchall()
    if duplicates:
        raise RuntimeError(
            "存在活动流水外部编号重复，迁移未改动流水。请核对并归档重复记录后重试："
            + "; ".join(f"portfolio={row[0]}, external_id={row[1]}, count={row[2]}" for row in duplicates)
        )
    predicate = sa.text("archived_at IS NULL AND external_id IS NOT NULL AND external_id <> ''")
    op.create_index("uq_portfolio_active_external_id", "portfolio_transactions",
                    ["portfolio_id", "external_id"], unique=True,
                    sqlite_where=predicate, postgresql_where=predicate)


def downgrade():
    op.drop_index("uq_portfolio_active_external_id", table_name="portfolio_transactions")
