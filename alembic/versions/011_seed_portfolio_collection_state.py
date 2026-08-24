"""seed the portfolio collection revision owner

Revision ID: 011_seed_portfolio_state
Revises: 010_portfolios_runtime
Create Date: 2026-08-23
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from alembic_support import has_table


revision: str = "011_seed_portfolio_state"
down_revision: Union[str, None] = "010_portfolios_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not has_table("portfolio_collection_state"):
        return

    connection = op.get_bind()
    state = sa.table(
        "portfolio_collection_state",
        sa.column("id", sa.String(length=32)),
        sa.column("revision", sa.Integer()),
        sa.column("active_portfolio_id", sa.String(length=120)),
        sa.column("updated_at", sa.DateTime()),
    )
    exists = connection.scalar(
        sa.select(sa.literal(True)).where(
            sa.exists(sa.select(state.c.id).where(state.c.id == "default"))
        )
    )
    if not exists:
        connection.execute(
            state.insert().values(
                id="default",
                revision=0,
                active_portfolio_id=None,
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )


def downgrade() -> None:
    # The singleton is durable application data after the first write. Keep it.
    return
