"""ORM-модель внешней identity пользователя."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.mixins import TimestampMixin


class ExternalIdentity(TimestampMixin, Base):
    """Связывает внутреннего пользователя со стабильной внешней identity."""

    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint(
            "external_issuer",
            "external_subject",
            name="uq_external_identities_issuer_subject",
        ),
        Index("ix_external_identities_app_user_id", "app_user_id"),
    )

    external_identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Внутренний идентификатор записи внешней identity",
    )
    app_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_users.app_user_id", ondelete="CASCADE"),
        nullable=False,
        comment="Внутренний пользователь приложения",
    )
    external_issuer: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Issuer проверенного внешнего токена",
    )
    external_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Стабильный subject пользователя у issuer",
    )
