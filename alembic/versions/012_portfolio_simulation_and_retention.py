"""separate portfolio simulations and index retention scans

Revision ID: 012_portfolio_perf
Revises: 011_seed_portfolio_state
Create Date: 2026-08-24
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa

from alembic_support import has_index, has_table


revision: str = "012_portfolio_perf"
down_revision: Union[str, None] = "011_seed_portfolio_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _simulation_fingerprint(payload: dict[str, Any]) -> str:
    simulation_input = {
        "assets": [
            {
                "symbol": asset.get("symbol", ""),
                "targetWeight": asset.get("targetWeight", 0),
            }
            for asset in payload.get("assets", [])
        ],
        "strategy": payload.get("strategy", {}),
        "simulation": payload.get("simulation", {}),
    }
    canonical = json.dumps(
        simulation_input,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade() -> None:
    if has_table("portfolio_records") and not has_table("portfolio_simulation_results"):
        op.create_table(
            "portfolio_simulation_results",
            sa.Column("portfolio_id", sa.String(length=120), nullable=False),
            sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["portfolio_id"],
                ["portfolio_records.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("portfolio_id"),
        )
        _extract_embedded_simulations()

    if has_table("klines") and not has_index("klines", "ix_klines_timeframe_timestamp"):
        op.create_index(
            "ix_klines_timeframe_timestamp",
            "klines",
            ["timeframe", "timestamp"],
            unique=False,
        )


def downgrade() -> None:
    if has_table("portfolio_simulation_results") and has_table("portfolio_records"):
        _restore_embedded_simulations()
        op.drop_table("portfolio_simulation_results")

    if has_table("klines") and has_index("klines", "ix_klines_timeframe_timestamp"):
        op.drop_index("ix_klines_timeframe_timestamp", table_name="klines")


def _extract_embedded_simulations() -> None:
    connection = op.get_bind()
    records = sa.table(
        "portfolio_records",
        sa.column("id", sa.String(length=120)),
        sa.column("payload", sa.JSON()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    simulations = sa.table(
        "portfolio_simulation_results",
        sa.column("portfolio_id", sa.String(length=120)),
        sa.column("source_fingerprint", sa.String(length=64)),
        sa.column("payload", sa.JSON()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in connection.execute(sa.select(records)).mappings():
        payload = dict(row["payload"] or {})
        result = payload.pop("lastSimulationResult", None)
        connection.execute(
            records.update().where(records.c.id == row["id"]).values(payload=payload)
        )
        if result is None:
            continue
        connection.execute(
            simulations.insert().values(
                portfolio_id=row["id"],
                source_fingerprint=_simulation_fingerprint(payload),
                payload=result,
                created_at=row["created_at"] or now,
                updated_at=row["updated_at"] or now,
            )
        )


def _restore_embedded_simulations() -> None:
    connection = op.get_bind()
    records = sa.table(
        "portfolio_records",
        sa.column("id", sa.String(length=120)),
        sa.column("payload", sa.JSON()),
    )
    simulations = sa.table(
        "portfolio_simulation_results",
        sa.column("portfolio_id", sa.String(length=120)),
        sa.column("payload", sa.JSON()),
    )
    for row in connection.execute(sa.select(simulations)).mappings():
        payload = connection.scalar(
            sa.select(records.c.payload).where(records.c.id == row["portfolio_id"])
        )
        if payload is None:
            continue
        restored = dict(payload)
        restored["lastSimulationResult"] = row["payload"]
        connection.execute(
            records.update()
            .where(records.c.id == row["portfolio_id"])
            .values(payload=restored)
        )
