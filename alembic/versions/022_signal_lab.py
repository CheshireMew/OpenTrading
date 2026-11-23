"""Add Signal Lab tables to the OpenTrading database."""
from alembic import op

from signal_lab.storage.sql import TABLES, schema_statements

revision = "022_signal_lab"
down_revision = "021_confirmed_candle_history"
branch_labels = None
depends_on = None


def upgrade():
    postgres = op.get_bind().dialect.name == "postgresql"
    for statement in schema_statements(postgres):
        op.execute(statement)


def downgrade():
    # Reverse dependency order. Alembic owns these tables.
    for name in reversed(TABLES):
        op.execute(f"DROP TABLE signal_lab_{name}")
