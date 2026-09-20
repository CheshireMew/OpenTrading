"""Add independent local backtest runs and ordered result records."""
from alembic import op
import sqlalchemy as sa

revision = "018_local_backtests"
down_revision = "017_research_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("local_backtest_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    op.create_index("ix_local_backtest_runs_status", "local_backtest_runs", ["status"])
    op.create_table("local_backtest_records",
        sa.Column("run_id", sa.String(64), sa.ForeignKey("local_backtest_runs.id"), primary_key=True),
        sa.Column("kind", sa.String(20), primary_key=True),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    op.create_index("ix_local_backtest_record_time", "local_backtest_records", ["run_id", "kind", "timestamp"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM local_backtest_runs")).scalar():
        raise RuntimeError("已有回测记录；降级前请先明确安排数据归档")
    op.drop_table("local_backtest_records")
    op.drop_table("local_backtest_runs")
