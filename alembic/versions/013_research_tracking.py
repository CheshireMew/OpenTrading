"""add durable research tracking workspace

Revision ID: 013_research_tracking
Revises: 012_portfolio_perf
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from alembic_support import has_table


revision: str = "013_research_tracking"
down_revision: Union[str, None] = "012_portfolio_perf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not has_table("research_watchlists"):
        op.create_table(
            "research_watchlists",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_research_watchlists_active_position",
            "research_watchlists",
            ["archived_at", "position"],
            unique=False,
        )

    if not has_table("research_watch_items"):
        op.create_table(
            "research_watch_items",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("watchlist_id", sa.String(length=120), nullable=False),
            sa.Column("symbol", sa.String(length=160), nullable=False),
            sa.Column("asset_class", sa.String(length=32), nullable=False),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("thesis", sa.Text(), nullable=False),
            sa.Column("target_price", sa.Float(), nullable=True),
            sa.Column("invalidation_price", sa.Float(), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("source_context", sa.JSON(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["watchlist_id"], ["research_watchlists.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("watchlist_id", "symbol", name="uq_research_watch_item_symbol"),
        )
        op.create_index(
            "ix_research_watch_items_symbol_active",
            "research_watch_items",
            ["symbol", "archived_at"],
            unique=False,
        )
        op.create_index(
            "ix_research_watch_items_list_position",
            "research_watch_items",
            ["watchlist_id", "archived_at", "position"],
            unique=False,
        )

    if not has_table("research_notes"):
        op.create_table(
            "research_notes",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("watch_item_id", sa.String(length=120), nullable=True),
            sa.Column("symbol", sa.String(length=160), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["watch_item_id"], ["research_watch_items.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_research_notes_symbol_occurred",
            "research_notes",
            ["symbol", "archived_at", "occurred_at"],
            unique=False,
        )

    if not has_table("research_alert_rules"):
        op.create_table(
            "research_alert_rules",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("watch_item_id", sa.String(length=120), nullable=True),
            sa.Column("symbol", sa.String(length=160), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("metric", sa.String(length=80), nullable=False),
            sa.Column("operator", sa.String(length=24), nullable=False),
            sa.Column("threshold", sa.Float(), nullable=False),
            sa.Column("secondary_threshold", sa.Float(), nullable=True),
            sa.Column("enabled", sa.Integer(), nullable=False),
            sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
            sa.Column("notification_channels", sa.JSON(), nullable=False),
            sa.Column("configuration", sa.JSON(), nullable=False),
            sa.Column("last_value", sa.Float(), nullable=True),
            sa.Column("last_evaluated_at", sa.DateTime(), nullable=True),
            sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["watch_item_id"], ["research_watch_items.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_research_alerts_enabled_symbol",
            "research_alert_rules",
            ["archived_at", "enabled", "symbol"],
            unique=False,
        )

    if not has_table("research_events"):
        op.create_table(
            "research_events",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("entity_type", sa.String(length=40), nullable=False),
            sa.Column("entity_id", sa.String(length=120), nullable=True),
            sa.Column("symbol", sa.String(length=160), nullable=True),
            sa.Column("kind", sa.String(length=60), nullable=False),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_research_events_timeline",
            "research_events",
            ["occurred_at", "kind"],
            unique=False,
        )
        op.create_index(
            "ix_research_events_entity",
            "research_events",
            ["entity_type", "entity_id", "occurred_at"],
            unique=False,
        )


def downgrade() -> None:
    for table_name in (
        "research_events",
        "research_alert_rules",
        "research_notes",
        "research_watch_items",
        "research_watchlists",
    ):
        if has_table(table_name):
            op.drop_table(table_name)
