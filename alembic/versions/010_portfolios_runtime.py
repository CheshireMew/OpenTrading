"""add durable portfolios and runtime component status

Revision ID: 010_portfolios_runtime
Revises: 009_performance_indexes
Create Date: 2026-08-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from alembic_support import has_table


revision: str = "010_portfolios_runtime"
down_revision: Union[str, None] = "009_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not has_table("portfolio_collection_state"):
        op.create_table(
            "portfolio_collection_state",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("active_portfolio_id", sa.String(length=120), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not has_table("portfolio_records"):
        op.create_table(
            "portfolio_records",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_portfolio_records_deleted_position",
            "portfolio_records",
            ["deleted_at", "position"],
            unique=False,
        )

    if not has_table("runtime_component_status"):
        op.create_table(
            "runtime_component_status",
            sa.Column("component", sa.String(length=80), nullable=False),
            sa.Column("owner_id", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=False),
            sa.Column("last_success_at", sa.DateTime(), nullable=True),
            sa.Column("last_failure_at", sa.DateTime(), nullable=True),
            sa.Column("next_run_at", sa.DateTime(), nullable=True),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("component"),
        )


def downgrade() -> None:
    if has_table("runtime_component_status"):
        op.drop_table("runtime_component_status")
    if has_table("portfolio_records"):
        op.drop_index("ix_portfolio_records_deleted_position", table_name="portfolio_records")
        op.drop_table("portfolio_records")
    if has_table("portfolio_collection_state"):
        op.drop_table("portfolio_collection_state")
