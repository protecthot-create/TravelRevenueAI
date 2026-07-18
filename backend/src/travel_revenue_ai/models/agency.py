"""Stub-модель Agency для MVP."""

import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from travel_revenue_ai.models.base import Base


class Agency(Base):
    """Временная MVP-заглушка до реализации полного data model для Agency."""

    __tablename__ = "agencies"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    signals: Mapped[list["Signal"]] = relationship(
        "Signal",
        back_populates="agency",
        lazy="selectin",
    )

    morning_briefs: Mapped[list["MorningBrief"]] = relationship(
        "MorningBrief",
        back_populates="agency",
        lazy="selectin",
    )
