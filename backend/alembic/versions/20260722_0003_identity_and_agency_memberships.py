"""Identity и agency membership foundation для CS10.

Revision ID: 20260722_0003
Revises: 20260722_0002
Create Date: 2026-07-22

Ревизия создаёт только пустую schema foundation. Она не выполняет bootstrap,
JIT provisioning, seed data или назначение owner.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260722_0003"
down_revision: Union[str, None] = "20260722_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_postgresql() -> None:
    """Блокирует применение CS10-ревизии к неподдерживаемой СУБД."""
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        raise RuntimeError(
            "Unsupported Alembic target database: "
            f"{dialect!r}. Revision {revision} supports PostgreSQL only."
        )


def upgrade() -> None:
    """Создаёт пустые identity и agency membership таблицы CS10."""
    _require_postgresql()

    op.create_table(
        "app_users",
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.PrimaryKeyConstraint("app_user_id", name="pk_app_users"),
    )

    op.create_table(
        "external_identities",
        sa.Column("external_identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_issuer", sa.String(length=255), nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=False),
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
            ["app_user_id"],
            ["app_users.app_user_id"],
            name="fk_external_identities_app_user_id_app_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("external_identity_id", name="pk_external_identities"),
        sa.UniqueConstraint(
            "external_issuer",
            "external_subject",
            name="uq_external_identities_issuer_subject",
        ),
    )
    op.create_index(
        "ix_external_identities_app_user_id",
        "external_identities",
        ["app_user_id"],
    )

    op.create_table(
        "agency_memberships",
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'member'"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
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
            name="fk_agency_memberships_agency_id_agencies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["app_users.app_user_id"],
            name="fk_agency_memberships_app_user_id_app_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "agency_id",
            "app_user_id",
            name="pk_agency_memberships",
        ),
        sa.CheckConstraint(
            "role IN ('member', 'owner')",
            name="ck_agency_memberships_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'revoked')",
            name="ck_agency_memberships_status",
        ),
    )
    op.create_index(
        "ix_agency_memberships_app_user_agency",
        "agency_memberships",
        ["app_user_id", "agency_id"],
    )


def downgrade() -> None:
    """Удаляет только объекты CS10 в обратном порядке зависимостей."""
    op.drop_index(
        "ix_agency_memberships_app_user_agency",
        table_name="agency_memberships",
    )
    op.drop_table("agency_memberships")

    op.drop_index(
        "ix_external_identities_app_user_id",
        table_name="external_identities",
    )
    op.drop_table("external_identities")
    op.drop_table("app_users")
