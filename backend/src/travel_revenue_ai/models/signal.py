"""SQLAlchemy-модель Signal для Travel Revenue AI.

Сигнал — это исходный сигнал из внешнего или внутреннего источника.
Сырые данные до нормализации и оценки.

Spec: docs/data_model.md, секция 3.
"""

import enum
import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import validates

from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.mixins import TimestampMixin


class SignalTypeEnum(str, enum.Enum):
    """Типы сигналов согласно спецификации."""

    opportunity = "opportunity"
    risk = "risk"
    market = "market"
    operational = "operational"


class SignalStatusEnum(str, enum.Enum):
    """Статусы обработки сигнала согласно спецификации."""

    new = "new"
    normalized = "normalized"
    scored = "scored"
    filtered = "filtered"
    rejected = "rejected"


class Signal(TimestampMixin, Base):
    """Модель Signal — исходный сигнал из источника данных.

    Сигнал поступает из Data Source и проходит через конвейер обработки:
    1. new — только что поступил
    2. normalized — приведён к единому формату
    3. scored — оценён Revenue Scoring Engine
    4. filtered — прошёл или не прошёл Filtering Engine
    5. rejected — отклонён (не прошёл фильтры)

    Атрибуты:
        signal_id: Уникальный идентификатор сигнала (UUID).
        agency_id: Ссылка на агентство-владелец.
        source_id: Ссылка на источник данных.
        signal_type: Тип сигнала (opportunity/risk/market/operational).
        raw_data: Сырые данные сигнала в JSON-формате.
        status: Текущий статус обработки.
        created_at: Дата и время поступления сигнала.
        updated_at: Дата и время последнего обновления.

    Связи:
        agency: Агентство-владелец сигнала.
        source: Источник данных сигнала.
        decision_cards: Исторические Decision Card, порождённые этим сигналом.
        action: Действие, связанное с этим сигналом (опционально).
    """

    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_type_status", "signal_type", "status"),
        Index("ix_signals_agency_created", "agency_id", "created_at"),
    )

    # Первичный ключ
    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный идентификатор сигнала",
    )

    # Внешние ключи
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.agency_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Ссылка на агентство-владелец",
    )

    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.source_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Ссылка на источник данных (nullable, т.к. SET NULL)",
    )

    # Основные поля
    signal_type: Mapped[SignalTypeEnum] = mapped_column(
        Enum(SignalTypeEnum, name="signal_type_enum", create_constraint=True),
        nullable=False,
        comment="Тип сигнала: opportunity / risk / market / operational",
    )

    raw_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Сырые данные сигнала в JSON-формате",
    )

    status: Mapped[SignalStatusEnum] = mapped_column(
        Enum(SignalStatusEnum, name="signal_status_enum", create_constraint=True),
        nullable=False,
        default=SignalStatusEnum.new,
        comment="Статус обработки: new / normalized / scored / filtered / rejected",
    )

    # Связи (обратные)
    agency: Mapped["Agency"] = relationship(
        "Agency",
        back_populates="signals",
        lazy="selectin",
    )

    source: Mapped[Optional["DataSource"]] = relationship(
        "DataSource",
        back_populates="signals",
        lazy="selectin",
    )

    decision_cards: Mapped[list["DecisionCard"]] = relationship(
        "DecisionCard",
        back_populates="signal",
        lazy="selectin",
    )

    action: Mapped[Optional["Action"]] = relationship(
        "Action",
        back_populates="signal",
        uselist=False,
        lazy="selectin",
    )

    @validates("raw_data")
    def validate_raw_data(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        """Проверяет, что raw_data является непустым JSON-объектом."""
        if not isinstance(value, dict):
            raise ValueError("raw_data должен быть JSON-объектом")
        return value

    @validates("signal_type")
    def validate_signal_type(self, key: str, value: SignalTypeEnum | str) -> SignalTypeEnum:
        """Проверяет допустимость типа сигнала."""
        if isinstance(value, str):
            try:
                return SignalTypeEnum(value)
            except ValueError as error:
                raise ValueError("Недопустимый тип сигнала") from error
        return value

    @validates("status")
    def validate_status(self, key: str, value: SignalStatusEnum | str) -> SignalStatusEnum:
        """Проверяет допустимость статуса сигнала."""
        if isinstance(value, str):
            try:
                return SignalStatusEnum(value)
            except ValueError as error:
                raise ValueError("Недопустимый статус сигнала") from error
        return value

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        return (
            f"<Signal(id={self.signal_id}, "
            f"type={self.signal_type}, "
            f"status={self.status}, "
            f"agency={self.agency_id})>"
        )

    def is_processed(self) -> bool:
        """Проверяет, прошёл ли сигнал полную обработку."""
        return self.status in ("filtered", "rejected")

    def is_rejected(self) -> bool:
        """Проверяет, был ли сигнал отклонён."""
        return self.status == "rejected"

    def can_be_scored(self) -> bool:
        """Проверяет, готов ли сигнал для оценки scoring engine."""
        return self.status == "normalized"

    def can_be_filtered(self) -> bool:
        """Проверяет, готов ли сигнал для фильтрации."""
        return self.status == "scored"


# Импорт для избежания циклических зависимостей
if TYPE_CHECKING:
    from travel_revenue_ai.models.agency import Agency
    from travel_revenue_ai.models.data_source import DataSource
    from travel_revenue_ai.models.decision_card import DecisionCard
    from travel_revenue_ai.models.action import Action