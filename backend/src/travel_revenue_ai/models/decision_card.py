"""SQLAlchemy-модель неизменяемой persisted DecisionCard."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.mixins import TimestampMixin


class DecisionCard(TimestampMixin, Base):
    """Исторически сохраняемая рекомендация, сгенерированная по Signal.

    Контентные поля карточки после создания не изменяются. Обновляться в
    последующих change set могут только lifecycle/feedback-поля ``status``,
    ``feedback_state`` и ``updated_at``.
    """

    __tablename__ = "decision_cards"
    __table_args__ = (
        Index("ix_decision_cards_agency_id", "agency_id"),
        Index("ix_decision_cards_signal_id", "signal_id"),
        Index("ix_decision_cards_execution_id", "execution_id"),
        Index("ix_decision_cards_generated_at", "generated_at"),
        Index("ix_decision_cards_status_feedback_state", "status", "feedback_state"),
    )

    decision_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Уникальный идентификатор сохранённой рекомендации",
    )

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.agency_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Агентство-владелец рекомендации",
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signals.signal_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Исходный сигнал; один Signal может иметь несколько карточек",
    )

    card_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Тип runtime-карточки: Opportunity/Risk/Market Insight/Operational Insight",
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    what_to_do: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Runtime DecisionCard.what_to_do — одна текстовая инструкция",
    )
    deadline: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Отображаемый дедлайн из runtime-карточки",
    )
    money_effect_raw: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        comment="Точный денежный эффект из runtime-сигнала",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="RUB",
        comment="ISO 4217 валюта денежного эффекта",
    )
    money_effect_display: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Внутренний PriorityLabel runtime-карточки",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        comment="Lifecycle статус карточки",
    )
    feedback_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        comment="Состояние feedback для карточки",
    )
    reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="Объяснение/trace расчёта",
    )
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Декомпозиция score и применённые модификаторы",
    )
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Аудит-метаданные генерации",
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    execution_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Идентификатор execution, создавшего карточку",
    )
    engine_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scoring_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    filtering_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    agency: Mapped["Agency"] = relationship(
        "Agency",
        back_populates="decision_cards",
        lazy="selectin",
    )
    signal: Mapped["Signal"] = relationship(
        "Signal",
        back_populates="decision_cards",
        lazy="selectin",
    )


if TYPE_CHECKING:
    from travel_revenue_ai.models.agency import Agency
    from travel_revenue_ai.models.signal import Signal