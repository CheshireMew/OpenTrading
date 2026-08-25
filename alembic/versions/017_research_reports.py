"""add reproducible research reports

Revision ID: 017_research_reports
Revises: 016_saved_market_screeners
Create Date: 2026-08-24
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from alembic_support import has_table

revision: str = "017_research_reports"
down_revision: Union[str, None] = "016_saved_market_screeners"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("research_reports"):
        return
    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("report_type", sa.String(length=40), nullable=False),
        sa.Column("symbol", sa.String(length=160), nullable=True),
        sa.Column("portfolio_id", sa.String(length=120), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("data_snapshot", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolio_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_reports_type_created",
        "research_reports",
        ["report_type", "archived_at", "created_at"],
        unique=False,
    )
    op.create_index("ix_research_reports_symbol_created", "research_reports", ["symbol", "created_at"], unique=False)


def downgrade() -> None:
    if has_table("research_reports"):
        op.drop_table("research_reports")
