"""ORM-модель membership пользователя в агентстве."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.mixins import TimestampMixin


class AgencyMembership(TimestampMixin, Base):
    """Связь пользователя с агентством и его ограниченной CS10-ролью."""

    __tablename__ = "agency_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('member', 'owner')",
            name="ck_agency_memberships_role",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'revoked')",
            name="ck_agency_memberships_status",
        ),
        Index(
            "ix_agency_memberships_app_user_agency",
            "app_user_id",
            "agency_id",
        ),
    )

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.agency_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Агентство, к которому относится membership",
    )
    app_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_users.app_user_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Внутренний пользователь приложения",
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="member",
        server_default=text("'member'"),
        comment="CS10-роль: member или owner",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        comment="Статус membership: active, suspended или revoked",
    )
