"""Index lossless cold OHLCV segments without changing existing candles."""
from alembic import op
import sqlalchemy as sa

revision = "023_kline_archive"
down_revision = "022_signal_lab"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kline_archive_segments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("first_timestamp", sa.BigInteger(), nullable=False),
        sa.Column("last_timestamp", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("finalized_count", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_kline_archive_scope_range", "kline_archive_segments",
                    ["symbol", "timeframe", "last_timestamp"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM kline_archive_segments LIMIT 1")).first():
        raise RuntimeError("Restore archived candles before downgrading; archive references must be preserved")
    op.drop_table("kline_archive_segments")
