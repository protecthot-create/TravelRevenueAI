"""Входные и выходные контракты Revenue Intelligence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    OpportunityGroup,
    OpportunityScore,
    Recommendation,
    RevenueImpact,
    RevenueRisk,
)


class RevenueIntelligenceErrorCode(StrEnum):
    """Коды штатных ошибок обработки отдельных компонентов."""

    COMPONENT_FAILURE = "component_failure"
    INVALID_COMPONENT_RESULT = "invalid_component_result"


class RevenueIntelligenceContext(BaseModel):
    """Безопасный контекст агентства и Intelligence metadata для анализа."""

    agency_id: UUID | None = None
    intelligence_metadata: dict[str, Any] = Field(default_factory=dict)
    agency_context: dict[str, Any] = Field(default_factory=dict)


class RevenueIntelligenceInput(BaseModel):
    """Снимок данных одного сигнала для автономной обработки.

    Контракт намеренно не импортирует ORM-модель Signal. Метод ``from_signal``
    принимает существующий Signal duck-typing и создаёт глубокие копии
    изменяемых полей, поэтому Engine не может изменить исходную ORM-сущность.
    """

    signal_id: UUID
    signal_type: str
    raw_data: dict[str, Any] = Field(default_factory=dict)
    context: RevenueIntelligenceContext = Field(default_factory=RevenueIntelligenceContext)
    received_at: datetime | None = None
    selection_limit: int = Field(default=5, ge=1)

    @classmethod
    def from_signal(
        cls,
        signal: Any,
        *,
        context: RevenueIntelligenceContext | None = None,
    ) -> "RevenueIntelligenceInput":
        """Создаёт независимый снимок существующего Signal без его изменения."""
        raw_data = deepcopy(getattr(signal, "raw_data", {}))
        metadata = raw_data.get("metadata", {})
        intelligence = metadata.get("intelligence", {}) if isinstance(metadata, dict) else {}

        return cls(
            signal_id=getattr(signal, "signal_id"),
            signal_type=str(getattr(signal, "signal_type")),
            raw_data=raw_data,
            context=context
            or RevenueIntelligenceContext(
                agency_id=getattr(signal, "agency_id", None),
                intelligence_metadata=deepcopy(intelligence)
                if isinstance(intelligence, dict)
                else {},
            ),
            received_at=getattr(signal, "created_at", None),
        )


class RevenueIntelligenceError(BaseModel):
    """Безопасная ошибка изолированного этапа, не прерывающая обработку."""

    component: str = Field(min_length=1)
    code: RevenueIntelligenceErrorCode
    message: str = Field(min_length=1)
    stage: str = Field(default="component", min_length=1)
    safe_message: str = Field(
        default="Компонент завершился с контролируемой ошибкой.",
        min_length=1,
    )
    opportunity_id: UUID | None = None


class RankedOpportunity(BaseModel):
    """Независимая позиция результата детерминированного ранжирования."""

    opportunity: BusinessOpportunity
    score: OpportunityScore
    rank: int = Field(ge=0)
    recommendations: list[Recommendation] = Field(default_factory=list)
    revenue_impact: RevenueImpact | None = None
    selection_reason: str = Field(min_length=1)


class OpportunityRankingResult(BaseModel):
    """Полный результат ранжирования и выбора возможностей."""

    ranked_opportunities: list[RankedOpportunity] = Field(default_factory=list)
    selected_opportunities: list[RankedOpportunity] = Field(default_factory=list)
    total_candidates: int = Field(default=0, ge=0)
    selection_limit: int = Field(default=5, ge=1)
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    errors: list[RevenueIntelligenceError] = Field(default_factory=list)


class RevenueIntelligenceResult(BaseModel):
    """Полный, в том числе пустой, результат работы Revenue Intelligence."""

    opportunities: list[BusinessOpportunity] = Field(default_factory=list)
    detected_opportunities: list[BusinessOpportunity] = Field(default_factory=list)
    risks: list[RevenueRisk] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    revenue_impacts: list[RevenueImpact] = Field(default_factory=list)
    groups: list[OpportunityGroup] = Field(default_factory=list)
    ranking_result: OpportunityRankingResult | None = None
    selected_opportunities: list[RankedOpportunity] = Field(default_factory=list)
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    errors: list[RevenueIntelligenceError] = Field(default_factory=list)
