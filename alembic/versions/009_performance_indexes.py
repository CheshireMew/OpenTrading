"""add performance indexes and indicator uniqueness

Revision ID: 009_performance_indexes
Revises: 008_drop_funding_rates
Create Date: 2026-08-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from alembic_support import has_index, has_table


revision: str = "009_performance_indexes"
down_revision: Union[str, None] = "008_drop_funding_rates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_index("klines", "ix_kline_sym_tf_ts"):
        op.drop_index("ix_kline_sym_tf_ts", table_name="klines")

    if not has_table("market_indicator_data"):
        return

    op.execute(
        sa.text(
            "DELETE FROM market_indicator_data "
            "WHERE id NOT IN ("
            "SELECT MIN(id) FROM market_indicator_data "
            "GROUP BY indicator_id, timestamp"
            ")"
        )
    )
    if has_index("market_indicator_data", "ix_indicator_data_id_ts"):
        op.drop_index("ix_indicator_data_id_ts", table_name="market_indicator_data")
    op.create_index(
        "ix_indicator_data_id_ts",
        "market_indicator_data",
        ["indicator_id", "timestamp"],
        unique=True,
    )


def downgrade() -> None:
    if has_index("market_indicator_data", "ix_indicator_data_id_ts"):
        op.drop_index("ix_indicator_data_id_ts", table_name="market_indicator_data")
        op.create_index(
            "ix_indicator_data_id_ts",
            "market_indicator_data",
            ["indicator_id", "timestamp"],
            unique=False,
        )
    if has_table("klines") and not has_index("klines", "ix_kline_sym_tf_ts"):
        op.create_index(
            "ix_kline_sym_tf_ts",
            "klines",
            ["symbol", "timeframe", "timestamp"],
            unique=False,
        )
