"""Stub-модель DecisionCard для MVP."""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from travel_revenue_ai.models.base import Base


class DecisionCard(Base):
    """Временная MVP-заглушка до реализации полного data model для DecisionCard."""

    __tablename__ = "decision_cards"

    decision_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signals.signal_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    signal: Mapped["Signal"] = relationship(
        "Signal",
        back_populates="decision_card",
        lazy="selectin",
    )
