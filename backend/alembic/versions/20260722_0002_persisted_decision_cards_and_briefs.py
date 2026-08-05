"""Persist immutable decision cards and morning brief snapshots.

Revision ID: 20260722_0002
Revises: 20260718_0001
Create Date: 2026-07-22

PostgreSQL is the only supported Alembic target database for this revision.
Legacy DecisionCard rows cannot satisfy the immutable Change Set 1 contract
without invented business data, so upgrade stops before every DDL operation
when such rows are present.

This revision is forward-only. A safe downgrade would have to discard immutable
DecisionCard content and reconstruct the retired MorningBrief → Action contract,
which this migration deliberately does not synthesize.
"""

from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260722_0002"
down_revision = "20260718_0001"
branch_labels = None
depends_on = None

MONEY_EFFECT_TYPE = sa.Numeric(precision=14, scale=2)
LEGACY_UNAVAILABLE_SNAPSHOT = (
    "'{\"schema_version\": \"legacy-unavailable\", "
    "\"content_available\": false}'::json"
)
EMPTY_JSON_ARRAY = "'[]'::json"


def _require_postgresql() -> None:
    """Блокирует применение PostgreSQL-only ревизии к неподдерживаемой СУБД."""
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        raise RuntimeError(
            "Unsupported Alembic target database: "
            f"{dialect!r}. Revision {revision} supports PostgreSQL only."
        )


def _constraint_names(
    table_name: str,
    *,
    constrained_columns: Iterable[str] | None = None,
    referenced_table: str | None = None,
    unique: bool = False,
) -> list[str]:
    """Возвращает фактические имена constraints из подключённой БД."""
    inspector = sa.inspect(op.get_bind())
    if unique:
        return [
            item["name"]
            for item in inspector.get_unique_constraints(table_name)
            if item.get("name")
            and (
                constrained_columns is None
                or item.get("column_names") == list(constrained_columns)
            )
        ]

    return [
        item["name"]
        for item in inspector.get_foreign_keys(table_name)
        if item.get("name")
        and (
            constrained_columns is None
            or item.get("constrained_columns") == list(constrained_columns)
        )
        and (
            referenced_table is None
            or item.get("referred_table") == referenced_table
        )
    ]


def _drop_indexes(table_name: str, column_name: str, *, unique: bool | None = None) -> None:
    """Удаляет индексы, совпадающие с legacy-колонкой."""
    inspector = sa.inspect(op.get_bind())
    for item in inspector.get_indexes(table_name):
        if item.get("column_names") != [column_name]:
            continue
        if unique is not None and bool(item.get("unique")) != unique:
            continue
        index_name = item.get("name")
        if index_name:
            op.drop_index(index_name, table_name=table_name)


def _require_empty_legacy_decision_cards() -> None:
    """Останавливает миграцию до DDL, когда legacy карточки нельзя честно перенести."""
    bind = op.get_bind()
    legacy_card_count = bind.execute(
        sa.text("SELECT count(*) FROM decision_cards")
    ).scalar_one()
    if not legacy_card_count:
        return

    sample_ids = bind.execute(
        sa.text(
            "SELECT decision_card_id::text FROM decision_cards "
            "ORDER BY decision_card_id LIMIT 20"
        )
    ).scalars().all()
    raise RuntimeError(
        "BLOCKED BY LEGACY DATA: decision_cards contains "
        f"{legacy_card_count} legacy row(s) without the immutable Change Set 1 "
        "content and agency provenance. No schema changes were applied. A "
        "separate, approved mapping or archival policy is required before "
        "assigning agency_id, content, money effects, scoring, audit data, and "
        f"generation provenance. Sample decision_card_id values: {', '.join(sample_ids)}"
    )


def upgrade() -> None:
    """Применяет Change Set 1 persistence schema без выдумывания legacy данных."""
    _require_postgresql()
    _require_empty_legacy_decision_cards()
    bind = op.get_bind()

    # Legacy DecisionCard table is confirmed empty before this point.
    for name in _constraint_names(
        "decision_cards", constrained_columns=["signal_id"], unique=True
    ):
        op.drop_constraint(name, "decision_cards", type_="unique")
    _drop_indexes("decision_cards", "signal_id", unique=True)

    for name in _constraint_names(
        "decision_cards", constrained_columns=["signal_id"], referenced_table="signals"
    ):
        op.drop_constraint(name, "decision_cards", type_="foreignkey")

    decision_card_columns = (
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("card_type", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("why_it_matters", sa.Text(), nullable=True),
        sa.Column("what_to_do", sa.Text(), nullable=True),
        sa.Column("deadline", sa.Text(), nullable=True),
        sa.Column("money_effect_raw", MONEY_EFFECT_TYPE, nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("money_effect_display", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("feedback_state", sa.String(length=32), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("audit_metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column("execution_id", sa.String(length=128), nullable=True),
        sa.Column("engine_version", sa.String(length=64), nullable=True),
        sa.Column("scoring_version", sa.String(length=64), nullable=True),
        sa.Column("filtering_version", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    for column in decision_card_columns:
        op.add_column("decision_cards", column)

    op.create_foreign_key(
        "fk_decision_cards_agency_id_agencies",
        "decision_cards",
        "agencies",
        ["agency_id"],
        ["agency_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_decision_cards_signal_id_signals",
        "decision_cards",
        "signals",
        ["signal_id"],
        ["signal_id"],
        ondelete="RESTRICT",
    )

    op.create_index("ix_decision_cards_agency_id", "decision_cards", ["agency_id"])
    op.create_index("ix_decision_cards_signal_id", "decision_cards", ["signal_id"])
    op.create_index("ix_decision_cards_execution_id", "decision_cards", ["execution_id"])
    op.create_index("ix_decision_cards_generated_at", "decision_cards", ["generated_at"])
    op.create_index(
        "ix_decision_cards_status_feedback_state",
        "decision_cards",
        ["status", "feedback_state"],
    )

    # The table was checked empty, so no recommendation content is backfilled.
    for column_name, column_type in (
        ("agency_id", postgresql.UUID(as_uuid=True)),
        ("card_type", sa.String(length=64)),
        ("title", sa.Text()),
        ("summary", sa.Text()),
        ("why_it_matters", sa.Text()),
        ("what_to_do", sa.Text()),
        ("deadline", sa.Text()),
        ("money_effect_raw", MONEY_EFFECT_TYPE),
        ("currency", sa.String(length=3)),
        ("money_effect_display", sa.Text()),
        ("score", sa.Float()),
        ("confidence", sa.Float()),
        ("priority", sa.String(length=32)),
        ("status", sa.String(length=32)),
        ("feedback_state", sa.String(length=32)),
        ("reasoning", sa.Text()),
        ("score_breakdown", postgresql.JSON(astext_type=sa.Text())),
        ("audit_metadata", postgresql.JSON(astext_type=sa.Text())),
        ("generated_at", sa.DateTime(timezone=True)),
        ("created_at", sa.DateTime(timezone=True)),
        ("updated_at", sa.DateTime(timezone=True)),
    ):
        op.alter_column(
            "decision_cards",
            column_name,
            existing_type=column_type,
            nullable=False,
        )

    # Preserve target server defaults for the three timestamp columns. ORM
    # onupdate remains application-side behavior, not a database trigger.
    for column_name in ("generated_at", "created_at", "updated_at"):
        op.alter_column(
            "decision_cards",
            column_name,
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        )

    # Preserve the legacy ordered lists but rename them to persisted-card IDs.
    op.alter_column(
        "morning_briefs",
        "top_opportunities",
        new_column_name="top_opportunity_card_ids",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
    )
    op.alter_column(
        "morning_briefs",
        "top_risks",
        new_column_name="top_risk_card_ids",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
    )

    brief_columns = (
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column("main_decision_card_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("market_insight_card_ids", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("opportunities_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("risks_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("market_insights_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("main_action_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("statistics_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("input_signal_ids", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_id", sa.String(length=128), nullable=True),
        sa.Column("trigger_type", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("scheduler_job_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("feature_flags_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("engine_version", sa.String(length=64), nullable=True),
        sa.Column("scoring_version", sa.String(length=64), nullable=True),
        sa.Column("filtering_version", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    for column in brief_columns:
        op.add_column("morning_briefs", column)

    # A PostgreSQL JSON literal is assigned as JSON, never serialized as a
    # quoted JSON string. COALESCE preserves any already populated partial data.
    bind.execute(
        sa.text(
            "UPDATE morning_briefs SET "
            "generated_at = COALESCE(generated_at, created_at, now()), "
            f"market_insight_card_ids = COALESCE(market_insight_card_ids, {EMPTY_JSON_ARRAY}), "
            f"opportunities_snapshot = COALESCE(opportunities_snapshot, {LEGACY_UNAVAILABLE_SNAPSHOT}), "
            f"risks_snapshot = COALESCE(risks_snapshot, {LEGACY_UNAVAILABLE_SNAPSHOT}), "
            f"market_insights_snapshot = COALESCE(market_insights_snapshot, {LEGACY_UNAVAILABLE_SNAPSHOT}), "
            f"summary_snapshot = COALESCE(summary_snapshot, {LEGACY_UNAVAILABLE_SNAPSHOT}), "
            f"statistics_snapshot = COALESCE(statistics_snapshot, {LEGACY_UNAVAILABLE_SNAPSHOT}), "
            f"input_signal_ids = COALESCE(input_signal_ids, {EMPTY_JSON_ARRAY}), "
            f"feature_flags_snapshot = COALESCE(feature_flags_snapshot, {LEGACY_UNAVAILABLE_SNAPSHOT}), "
            "updated_at = COALESCE(updated_at, created_at, now()), "
            "idempotency_key = COALESCE(idempotency_key, 'legacy:' || brief_id::text)"
        )
    )

    for column_name in (
        "generated_at",
        "market_insight_card_ids",
        "opportunities_snapshot",
        "risks_snapshot",
        "market_insights_snapshot",
        "summary_snapshot",
        "statistics_snapshot",
        "input_signal_ids",
        "idempotency_key",
        "feature_flags_snapshot",
        "updated_at",
    ):
        column_type: sa.types.TypeEngine[object]
        if column_name in {
            "market_insight_card_ids",
            "opportunities_snapshot",
            "risks_snapshot",
            "market_insights_snapshot",
            "summary_snapshot",
            "statistics_snapshot",
            "input_signal_ids",
            "feature_flags_snapshot",
        }:
            column_type = postgresql.JSON(astext_type=sa.Text())
        elif column_name in {"generated_at", "updated_at"}:
            column_type = sa.DateTime(timezone=True)
        else:
            column_type = sa.String(length=255)
        op.alter_column(
            "morning_briefs",
            column_name,
            existing_type=column_type,
            nullable=False,
        )

    for column_name in ("generated_at", "updated_at"):
        op.alter_column(
            "morning_briefs",
            column_name,
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        )

    op.create_foreign_key(
        "fk_morning_briefs_main_decision_card_id_decision_cards",
        "morning_briefs",
        "decision_cards",
        ["main_decision_card_id"],
        ["decision_card_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_morning_briefs_main_decision_card_id",
        "morning_briefs",
        ["main_decision_card_id"],
    )
    op.create_index(
        "ix_morning_briefs_agency_idempotency_key",
        "morning_briefs",
        ["agency_id", "idempotency_key"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_morning_briefs_main_action_snapshot_for_main_card",
        "morning_briefs",
        "("
        "main_decision_card_id IS NULL AND main_action_snapshot IS NULL"
        ") OR ("
        "main_decision_card_id IS NOT NULL AND main_action_snapshot IS NOT NULL"
        ")",
    )

    # Retire only the legacy MorningBrief → Action reference; Action itself
    # remains a legacy table/model and is intentionally not removed.
    for name in _constraint_names(
        "morning_briefs",
        constrained_columns=["main_action_id"],
        referenced_table="actions",
    ):
        op.drop_constraint(name, "morning_briefs", type_="foreignkey")
    _drop_indexes("morning_briefs", "main_action_id")
    op.drop_column("morning_briefs", "main_action_id")


def downgrade() -> None:
    """Блокирует опасный откат до выполнения любого DDL."""
    raise RuntimeError(
        f"Revision {revision} is forward-only. Downgrade would discard immutable "
        "DecisionCard data and cannot honestly recreate retired MorningBrief → "
        "Action references. Roll back with PostgreSQL backup/restore or apply a "
        "new forward corrective migration."
    )