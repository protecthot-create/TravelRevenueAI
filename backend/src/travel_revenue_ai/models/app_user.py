"""ORM-модель внутреннего пользователя приложения."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.mixins import TimestampMixin


class AppUser(TimestampMixin, Base):
    """Канонический пользователь приложения, независимый от Clerk identity."""

    __tablename__ = "app_users"

    app_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Внутренний идентификатор пользователя приложения",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="Глобально разрешён ли пользователь к работе в приложении",
    )
