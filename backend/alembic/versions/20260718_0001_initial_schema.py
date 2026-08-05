"""Immutable PostgreSQL baseline schema before Change Set 1.

Revision ID: 20260718_0001
Revises:
Create Date: 2026-07-18

This revision intentionally contains explicit historical DDL. Do not import ORM
metadata here: later model changes must never alter the schema created by this
baseline.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260718_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


signal_type_enum = postgresql.ENUM(
    "opportunity",
    "risk",
    "market",
    "operational",
    name="signal_type_enum",
    create_type=False,
)
signal_status_enum = postgresql.ENUM(
    "new",
    "normalized",
    "scored",
    "filtered",
    "rejected",
    name="signal_status_enum",
    create_type=False,
)
data_source_type_enum = postgresql.ENUM(
    "email",
    "telegram",
    "rss",
    "crm",
    "http_api",
    name="data_source_type_enum",
    create_type=False,
)
sync_status_enum = postgresql.ENUM(
    "never_synced",
    "success",
    "error",
    "disabled",
    name="sync_status_enum",
    create_type=False,
)
morning_brief_status_enum = postgresql.ENUM(
    "draft",
    "sent",
    "read",
    name="morning_brief_status_enum",
    create_type=False,
)


def upgrade() -> None:
    """Создаёт зафиксированную legacy-схему до Change Set 1."""
    bind = op.get_bind()

    # PostgreSQL is the canonical migration database. Explicit enum creation
    # keeps this historical schema independent from current ORM metadata.
    signal_type_enum.create(bind, checkfirst=True)
    signal_status_enum.create(bind, checkfirst=True)
    data_source_type_enum.create(bind, checkfirst=True)
    sync_status_enum.create(bind, checkfirst=True)
    morning_brief_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "agencies",
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("agency_id", name="pk_agencies"),
    )

    op.create_table(
        "data_sources",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_type", data_source_type_enum, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("credentials", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("settings", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("last_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sync_status_enum, nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["agency_id"],
            ["agencies.agency_id"],
            name="fk_data_sources_agency_id_agencies",
        ),
        sa.PrimaryKeyConstraint("source_id", name="pk_data_sources"),
    )
    op.create_index("ix_data_sources_agency_id", "data_sources", ["agency_id"])
    op.create_index("ix_data_sources_source_type", "data_sources", ["source_type"])

    op.create_table(
        "signals",
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signal_type", signal_type_enum, nullable=False),
        sa.Column("raw_data", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("status", signal_status_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["agency_id"],
            ["agencies.agency_id"],
            name="fk_signals_agency_id_agencies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.source_id"],
            name="fk_signals_source_id_data_sources",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("signal_id", name="pk_signals"),
    )
    op.create_index("ix_signals_agency_id", "signals", ["agency_id"])
    op.create_index("ix_signals_source_id", "signals", ["source_id"])
    op.create_index("ix_signals_type_status", "signals", ["signal_type", "status"])
    op.create_index("ix_signals_agency_created", "signals", ["agency_id", "created_at"])

    op.create_table(
        "actions",
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.signal_id"],
            name="fk_actions_signal_id_signals",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("action_id", name="pk_actions"),
        sa.UniqueConstraint("signal_id", name="uq_actions_signal_id"),
    )

    # Historical stub: one legacy card per signal, without Change Set 1 content.
    op.create_table(
        "decision_cards",
        sa.Column("decision_card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.signal_id"],
            name="fk_decision_cards_signal_id_signals",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("decision_card_id", name="pk_decision_cards"),
        sa.UniqueConstraint("signal_id", name="uq_decision_cards_signal_id"),
    )

    op.create_table(
        "morning_briefs",
        sa.Column("brief_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", morning_brief_status_enum, nullable=False),
        sa.Column("top_opportunities", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("top_risks", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("main_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agency_id"],
            ["agencies.agency_id"],
            name="fk_morning_briefs_agency_id_agencies",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["main_action_id"],
            ["actions.action_id"],
            name="fk_morning_briefs_main_action_id_actions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("brief_id", name="pk_morning_briefs"),
    )
    op.create_index(
        "ix_morning_briefs_agency_date",
        "morning_briefs",
        ["agency_id", "date"],
        unique=True,
    )
    op.create_index(
        "ix_morning_briefs_main_action_id",
        "morning_briefs",
        ["main_action_id"],
    )


def downgrade() -> None:
    """Удаляет только объекты зафиксированной legacy-схемы."""
    bind = op.get_bind()

    op.drop_index("ix_morning_briefs_main_action_id", table_name="morning_briefs")
    op.drop_index("ix_morning_briefs_agency_date", table_name="morning_briefs")
    op.drop_table("morning_briefs")
    op.drop_table("decision_cards")
    op.drop_table("actions")
    op.drop_index("ix_signals_agency_created", table_name="signals")
    op.drop_index("ix_signals_type_status", table_name="signals")
    op.drop_index("ix_signals_source_id", table_name="signals")
    op.drop_index("ix_signals_agency_id", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_data_sources_source_type", table_name="data_sources")
    op.drop_index("ix_data_sources_agency_id", table_name="data_sources")
    op.drop_table("data_sources")
    op.drop_table("agencies")

    morning_brief_status_enum.drop(bind, checkfirst=True)
    sync_status_enum.drop(bind, checkfirst=True)
    data_source_type_enum.drop(bind, checkfirst=True)
    signal_status_enum.drop(bind, checkfirst=True)
    signal_type_enum.drop(bind, checkfirst=True)