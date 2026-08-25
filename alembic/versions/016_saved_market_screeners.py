"""add saved market screeners and historical runs

Revision ID: 016_saved_market_screeners
Revises: 015_trade_signal_review
Create Date: 2026-08-24
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from alembic_support import has_table

revision: str = "016_saved_market_screeners"
down_revision: Union[str, None] = "015_trade_signal_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not has_table("saved_market_screeners"):
        op.create_table(
            "saved_market_screeners",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("filters", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_saved_screeners_active_updated", "saved_market_screeners", ["archived_at", "updated_at"], unique=False
        )
    if not has_table("market_screener_runs"):
        op.create_table(
            "market_screener_runs",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("screener_id", sa.String(length=120), nullable=False),
            sa.Column("filters_snapshot", sa.JSON(), nullable=False),
            sa.Column("result_items", sa.JSON(), nullable=False),
            sa.Column("result_count", sa.Integer(), nullable=False),
            sa.Column("snapshot_as_of", sa.DateTime(), nullable=False),
            sa.Column("evaluated_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["screener_id"], ["saved_market_screeners.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_screener_runs_history", "market_screener_runs", ["screener_id", "snapshot_as_of"], unique=False
        )
        op.create_index("ix_screener_runs_evaluated", "market_screener_runs", ["evaluated_at"], unique=False)


def downgrade() -> None:
    if has_table("market_screener_runs"):
        op.drop_table("market_screener_runs")
    if has_table("saved_market_screeners"):
        op.drop_table("saved_market_screeners")
