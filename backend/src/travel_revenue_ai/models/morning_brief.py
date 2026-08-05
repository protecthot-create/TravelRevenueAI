"""SQLAlchemy-модель исторического MorningBrief."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from travel_revenue_ai.models.base import Base
from travel_revenue_ai.models.mixins import TimestampMixin


class MorningBriefStatusEnum(str, enum.Enum):
    """Статусы отправки и прочтения брифа."""

    draft = "draft"
    sent = "sent"
    read = "read"


class MorningBrief(TimestampMixin, Base):
    """Неизменяемый исторический snapshot утреннего брифа.

    Массивы идентификаторов сохраняют порядок выбора карточек. Snapshot-поля
    намеренно не зависят от будущих изменений live-состояния DecisionCard.
    """

    __tablename__ = "morning_briefs"
    __table_args__ = (
        Index("ix_morning_briefs_agency_date", "agency_id", "date", unique=True),
        Index(
            "ix_morning_briefs_agency_idempotency_key",
            "agency_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_morning_briefs_main_decision_card_id", "main_decision_card_id"),
        CheckConstraint(
            "("
            "main_decision_card_id IS NULL AND main_action_snapshot IS NULL"
            ") OR ("
            "main_decision_card_id IS NOT NULL AND main_action_snapshot IS NOT NULL"
            ")",
            name="ck_morning_briefs_main_action_snapshot_for_main_card",
        ),
    )

    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.agency_id", ondelete="RESTRICT"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[MorningBriefStatusEnum] = mapped_column(
        Enum(MorningBriefStatusEnum, name="morning_brief_status_enum", create_constraint=True),
        nullable=False,
        default=MorningBriefStatusEnum.draft,
    )
    main_decision_card_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_cards.decision_card_id", ondelete="RESTRICT"),
        nullable=True,
    )

    top_opportunity_card_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    top_risk_card_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    market_insight_card_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    opportunities_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    risks_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    market_insights_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    main_action_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    statistics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    input_signal_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    execution_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    trigger_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    scheduler_job_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_flags_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    engine_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scoring_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    filtering_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    agency: Mapped["Agency"] = relationship(
        "Agency", back_populates="morning_briefs", lazy="selectin"
    )
    main_decision_card: Mapped[Optional["DecisionCard"]] = relationship(
        "DecisionCard", foreign_keys=[main_decision_card_id], lazy="selectin"
    )

    @validates("status")
    def validate_status(
        self, key: str, value: MorningBriefStatusEnum | str
    ) -> MorningBriefStatusEnum:
        """Нормализует строковое значение статуса."""
        return MorningBriefStatusEnum(value)

    @property
    def opportunities_count(self) -> int:
        """Возвращает число opportunity-карточек."""
        return len(self.top_opportunity_card_ids)

    @property
    def risks_count(self) -> int:
        """Возвращает число risk-карточек."""
        return len(self.top_risk_card_ids)


if TYPE_CHECKING:
    from travel_revenue_ai.models.agency import Agency
    from travel_revenue_ai.models.decision_card import DecisionCard