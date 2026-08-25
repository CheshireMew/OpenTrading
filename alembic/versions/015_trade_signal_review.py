"""add trade signal outcome tracking

Revision ID: 015_trade_signal_review
Revises: 014_portfolio_ledger
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from alembic_support import has_table


revision: str = "015_trade_signal_review"
down_revision: Union[str, None] = "014_portfolio_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("trade_signal_records"):
        return
    op.create_table(
        "trade_signal_records",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=160), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("signal_status", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=True),
        sa.Column("entry", sa.Float(), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("stop", sa.Float(), nullable=True),
        sa.Column("risk_reward", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("risk_amount", sa.Float(), nullable=True),
        sa.Column("style", sa.String(length=40), nullable=True),
        sa.Column("strategy", sa.String(length=80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("entry_time", sa.BigInteger(), nullable=True),
        sa.Column("market_snapshot", sa.JSON(), nullable=False),
        sa.Column("outcome_status", sa.String(length=32), nullable=False),
        sa.Column("outcome_price", sa.Float(), nullable=True),
        sa.Column("target_hit_at", sa.DateTime(), nullable=True),
        sa.Column("stop_hit_at", sa.DateTime(), nullable=True),
        sa.Column("mfe_pct", sa.Float(), nullable=True),
        sa.Column("mae_pct", sa.Float(), nullable=True),
        sa.Column("forward_returns", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trade_signals_pending",
        "trade_signal_records",
        ["archived_at", "outcome_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_trade_signals_symbol_time", "trade_signal_records", ["symbol", "timeframe", "created_at"], unique=False
    )
    op.create_index(
        "ix_trade_signals_source_outcome",
        "trade_signal_records",
        ["source", "outcome_status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    if has_table("trade_signal_records"):
        op.drop_table("trade_signal_records")
