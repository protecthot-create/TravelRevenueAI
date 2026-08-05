"""ORM-модель конфигурации внешнего источника данных."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.mixins import TimestampMixin


class DataSourceTypeEnum(str, enum.Enum):
    """Поддерживаемые категории внешних источников."""

    email = "email"
    telegram = "telegram"
    rss = "rss"
    crm = "crm"
    http_api = "http_api"


class SyncStatusEnum(str, enum.Enum):
    """Текущее состояние последней синхронизации источника."""

    never_synced = "never_synced"
    success = "success"
    error = "error"
    disabled = "disabled"


class DataSource(TimestampMixin, Base):
    """Конфигурация подключаемого источника данных агентства.

    Модель определяет только структуру ORM. Миграция таблицы и подключение
    реальных внешних систем не входят в Sprint 6.0.
    """

    __tablename__ = "data_sources"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.agency_id"),
        nullable=False,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[DataSourceTypeEnum] = mapped_column(
        Enum(DataSourceTypeEnum, name="data_source_type_enum"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    credentials: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[SyncStatusEnum] = mapped_column(
        Enum(SyncStatusEnum, name="sync_status_enum"),
        nullable=False,
        default=SyncStatusEnum.never_synced,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    agency: Mapped["Agency"] = relationship(
        "Agency",
        lazy="selectin",
    )
    signals: Mapped[list["Signal"]] = relationship(
        "Signal",
        back_populates="source",
        lazy="selectin",
    )