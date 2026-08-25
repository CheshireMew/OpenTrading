"""add portfolio transaction ledger

Revision ID: 014_portfolio_ledger
Revises: 013_research_tracking
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from alembic_support import has_table


revision: str = "014_portfolio_ledger"
down_revision: Union[str, None] = "013_research_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("portfolio_transactions"):
        return
    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("portfolio_id", sa.String(length=120), nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("cash_amount", sa.Float(), nullable=False),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("fee_currency", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolio_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portfolio_transactions_timeline",
        "portfolio_transactions",
        ["portfolio_id", "archived_at", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_transactions_symbol",
        "portfolio_transactions",
        ["portfolio_id", "symbol", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    if has_table("portfolio_transactions"):
        op.drop_table("portfolio_transactions")
