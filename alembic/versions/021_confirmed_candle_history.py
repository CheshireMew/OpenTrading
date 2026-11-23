"""Keep unconfirmed cached bars out of finalized historical data."""
from alembic import op
import sqlalchemy as sa

revision = "021_confirmed_candle_history"
down_revision = "020_ledger_request_receipts"
branch_labels = None
depends_on = None


def upgrade():
    # Older rows have no evidence of when their close was observed. Preserve
    # them, but revalidate requested windows lazily before using them as history.
    op.add_column("klines", sa.Column("finalized", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("klines", "finalized")
