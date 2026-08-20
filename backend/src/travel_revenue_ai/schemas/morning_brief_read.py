"""Публичные read-only DTO для persisted Morning Brief."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MorningBriefDecisionCardDTO(BaseModel):
    """Разрешённое публичное представление persisted DecisionCard."""

    decision_card_id: UUID
    card_type: str
    title: str
    summary: str
    why_it_matters: str
    what_to_do: str
    deadline: str
    money_effect_display: str
    score: float
    confidence: float
    priority: str
    status: str
    feedback_state: str


class MorningBriefReadDTO(BaseModel):
    """Полное публичное представление persisted MorningBrief."""

    brief_id: UUID
    agency_id: UUID
    brief_date: date
    generated_at: datetime
    status: str
    summary_text: str
    opportunity_cards: list[MorningBriefDecisionCardDTO]
    risk_cards: list[MorningBriefDecisionCardDTO]
    market_insight_cards: list[MorningBriefDecisionCardDTO]
    main_decision_card: MorningBriefDecisionCardDTO | None


class MorningBriefHistoryItemDTO(BaseModel):
    """Краткая read-only запись истории утренних брифов."""

    brief_id: UUID
    brief_date: date
    generated_at: datetime
    status: str
    summary_text: str
    opportunity_count: int = Field(ge=0)
    risk_count: int = Field(ge=0)
    market_insight_count: int = Field(ge=0)
    total_card_count: int = Field(ge=0)
