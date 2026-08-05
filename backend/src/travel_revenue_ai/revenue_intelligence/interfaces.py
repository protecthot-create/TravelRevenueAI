"""Интерфейсы расширения Revenue Intelligence без инфраструктурных зависимостей."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from travel_revenue_ai.revenue_intelligence.contracts import (
    OpportunityRankingResult,
    RevenueIntelligenceContext,
    RevenueIntelligenceInput,
)
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityGroup,
    Recommendation,
    RevenueImpact,
    UrgencyLevel,
)


@runtime_checkable
class OpportunityDetector(Protocol):
    """Находит бизнес-возможности в снимке входного сигнала."""

    def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
        """Возвращает обнаруженные возможности."""


@runtime_checkable
class RevenueEstimator(Protocol):
    """Оценивает диапазон влияния возможности на выручку."""

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> RevenueImpact | None:
        """Возвращает оценку либо ``None``, если данных недостаточно."""


@runtime_checkable
class UrgencyEstimator(Protocol):
    """Определяет срочность возможности."""

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> UrgencyLevel:
        """Возвращает уровень срочности."""


@runtime_checkable
class ConfidenceEstimator(Protocol):
    """Определяет уверенность в возможности."""

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> ConfidenceLevel:
        """Возвращает уровень уверенности."""


@runtime_checkable
class RecommendationBuilder(Protocol):
    """Создаёт конкретные рекомендации для возможности."""

    def build(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> list[Recommendation]:
        """Возвращает рекомендации либо пустой список."""


@runtime_checkable
class OpportunityGrouper(Protocol):
    """Объединяет связанные возможности в группы."""

    def group(
        self,
        opportunities: list[BusinessOpportunity],
        context: RevenueIntelligenceContext,
    ) -> list[OpportunityGroup]:
        """Возвращает группы возможностей."""


@runtime_checkable
class OpportunityRanker(Protocol):
    """Ранжирует возможности и выбирает стабильный TOP-N без побочных эффектов."""

    def rank(
        self,
        opportunities: Sequence[BusinessOpportunity],
        *,
        revenue_impacts: Mapping[UUID, RevenueImpact | None] | None = None,
        recommendations: Mapping[UUID, Sequence[Recommendation]] | None = None,
        context: RevenueIntelligenceContext | None = None,
        limit: int = 5,
    ) -> OpportunityRankingResult:
        """Возвращает ранжированный результат и выбранные позиции."""


@runtime_checkable
class BusinessRule(Protocol):
    """Детерминированное правило, допустимое для будущих компонентов."""

    def applies(
        self,
        input_data: RevenueIntelligenceInput,
        context: RevenueIntelligenceContext,
    ) -> bool:
        """Сообщает, применимо ли правило к входным данным."""