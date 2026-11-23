"""Persist atomic ledger command receipts for retry-safe writes."""
from alembic import op
import sqlalchemy as sa

revision = "020_ledger_request_receipts"
down_revision = "019_atomic_ledger_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolio_ledger_requests",
        sa.Column("portfolio_id", sa.String(120), sa.ForeignKey("portfolio_records.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("request_id", sa.String(120), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("portfolio_ledger_requests")
