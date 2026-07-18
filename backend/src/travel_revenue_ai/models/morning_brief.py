"""SQLAlchemy-модель MorningBrief для Travel Revenue AI.

Morning Brief — ежедневный брифинг, собранный из приоритетных Decision Card.
Содержит top-возможности, top-риски и главное действие дня.

Spec: docs/data_model.md, секция 5.
"""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, JSON, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import validates

from travel_revenue_ai.models.base import Base


class MorningBriefStatusEnum(str, enum.Enum):
    """Статусы брифа согласно спецификации."""

    draft = "draft"  # Черновик, ещё не отправлен
    sent = "sent"  # Отправлен пользователю
    read = "read"  # Прочитан пользователем


class MorningBrief(Base):
    """Модель MorningBrief — ежедневный брифинг для агентства.

    Брифинг формируется из приоритетных Decision Card и содержит:
    - top-5 возможностей;
    - top-3 рисков;
    - главное действие дня;
    - краткий summary-текст.

    Жизненный цикл:
    1. draft — бриф сгенерирован, но ещё не отправлен
    2. sent — отправлен пользователю (email, telegram и т.д.)
    3. read — пользователь открыл бриф

    Атрибуты:
        brief_id: Уникальный идентификатор брифа (UUID).
        agency_id: Ссылка на агентство-владелец.
        date: Дата брифа (без времени).
        top_opportunities: Список UUID Decision Card с топ-возможностями (JSON).
        top_risks: Список UUID Decision Card с топ-рисками (JSON).
        main_action_id: UUID главного действия дня (nullable).
        summary_text: Краткий текст брифа для отображения.
        status: Текущий статус брифа.
        created_at: Дата и время создания.
        sent_at: Дата и время отправки (nullable).

    Связи:
        agency: Агентство-владелец брифа.
        main_action: Главное действие дня (опционально).
    """

    __tablename__ = "morning_briefs"
    __table_args__ = (
        # Индекс для быстрого поиска брифов по агентству и дате
        Index("ix_morning_briefs_agency_date", "agency_id", "date"),
        # Уникальный индекс: один бриф на агентство на дату
        Index(
            "ix_morning_briefs_agency_date_unique",
            "agency_id",
            "date",
            unique=True,
        ),
    )

    # Первичный ключ
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный идентификатор брифа",
    )

    # Внешний ключ на агентство
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.agency_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Ссылка на агентство-владелец",
    )

    # Дата брифа (без времени — один бриф на дату)
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Дата брифа",
    )

    # JSON-поля со списками Decision Card
    top_opportunities: Mapped[list[uuid.UUID]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Список UUID Decision Card с топ-возможностями (top-5)",
    )

    top_risks: Mapped[list[uuid.UUID]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Список UUID Decision Card с топ-рисками (top-3)",
    )

    # Главное действие дня (опционально)
    main_action_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("actions.action_id", ondelete="SET NULL"),
        nullable=True,
        comment="UUID главного действия дня",
    )

    # Текст брифа
    summary_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Краткий текст брифа для отображения",
    )

    # Статус брифа
    status: Mapped[MorningBriefStatusEnum] = mapped_column(
        Enum(
            MorningBriefStatusEnum,
            name="morning_brief_status_enum",
            create_constraint=True,
        ),
        nullable=False,
        default=MorningBriefStatusEnum.draft,
        comment="Статус: draft / sent / read",
    )

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Дата создания брифа",
    )

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата отправки брифа",
    )

    # Связи
    agency: Mapped["Agency"] = relationship(
        "Agency",
        back_populates="morning_briefs",
        lazy="selectin",
    )

    main_action: Mapped[Optional["Action"]] = relationship(
        "Action",
        back_populates="morning_brief",
        lazy="selectin",
    )

    # --- Валидаторы ---

    @validates("top_opportunities")
    def validate_top_opportunities(
        self, key: str, value: list[uuid.UUID] | list[str]
    ) -> list[uuid.UUID]:
        """Проверяет, что top_opportunities — список UUID."""
        if not isinstance(value, list):
            raise ValueError("top_opportunities должен быть списком")
        result: list[uuid.UUID] = []
        for item in value:
            if isinstance(item, uuid.UUID):
                result.append(item)
            elif isinstance(item, str):
                try:
                    result.append(uuid.UUID(item))
                except ValueError as error:
                    raise ValueError(
                        f"Недопустимый UUID в top_opportunities: '{item}'"
                    ) from error
            else:
                raise ValueError(
                    f"Элемент top_opportunities должен быть UUID или строкой, "
                    f"получен {type(item).__name__}"
                )
        # Ограничиваем top-5 согласно спецификации
        if len(result) > 5:
            raise ValueError("top_opportunities не может содержать более 5 элементов")
        return result

    @validates("top_risks")
    def validate_top_risks(
        self, key: str, value: list[uuid.UUID] | list[str]
    ) -> list[uuid.UUID]:
        """Проверяет, что top_risks — список UUID."""
        if not isinstance(value, list):
            raise ValueError("top_risks должен быть списком")
        result: list[uuid.UUID] = []
        for item in value:
            if isinstance(item, uuid.UUID):
                result.append(item)
            elif isinstance(item, str):
                try:
                    result.append(uuid.UUID(item))
                except ValueError as error:
                    raise ValueError(
                        f"Недопустимый UUID в top_risks: '{item}'"
                    ) from error
            else:
                raise ValueError(
                    f"Элемент top_risks должен быть UUID или строкой, "
                    f"получен {type(item).__name__}"
                )
        # Ограничиваем top-3 согласно спецификации
        if len(result) > 3:
            raise ValueError("top_risks не может содержать более 3 элементов")
        return result

    @validates("summary_text")
    def validate_summary_text(self, key: str, value: str) -> str:
        """Проверяет, что summary_text не пустой."""
        if not isinstance(value, str):
            raise ValueError("summary_text должен быть строкой")
        if len(value.strip()) == 0:
            raise ValueError("summary_text не может быть пустым")
        return value

    @validates("status")
    def validate_status(
        self, key: str, value: MorningBriefStatusEnum | str
    ) -> MorningBriefStatusEnum:
        """Проверяет допустимость статуса брифа."""
        if isinstance(value, str):
            try:
                return MorningBriefStatusEnum(value)
            except ValueError as error:
                raise ValueError(
                    f"Недопустимый статус брифа: '{value}'. "
                    f"Допустимые: {[s.value for s in MorningBriefStatusEnum]}"
                ) from error
        return value

    # --- Методы-геттеры ---

    @property
    def opportunities_count(self) -> int:
        """Возвращает количество возможностей в брифе."""
        return len(self.top_opportunities)

    @property
    def risks_count(self) -> int:
        """Возвращает количество рисков в брифе."""
        return len(self.top_risks)

    @property
    def is_draft(self) -> bool:
        """Проверяет, является ли бриф черновиком."""
        return self.status == MorningBriefStatusEnum.draft

    @property
    def is_sent(self) -> bool:
        """Проверяет, отправлен ли бриф."""
        return self.status == MorningBriefStatusEnum.sent

    @property
    def is_read(self) -> bool:
        """Проверяет, прочитан ли бриф."""
        return self.status == MorningBriefStatusEnum.read

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        return (
            f"<MorningBrief(id={self.brief_id}, "
            f"agency={self.agency_id}, "
            f"date={self.date}, "
            f"status={self.status.value}, "
            f"opportunities={self.opportunities_count}, "
            f"risks={self.risks_count})>"
        )


# Импорт для избежания циклических зависимостей
if TYPE_CHECKING:
    from travel_revenue_ai.models.agency import Agency
    from travel_revenue_ai.models.action import Action