"""Детерминированное ранжирование бизнес-возможностей без операций ввода-вывода."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from uuid import UUID

from travel_revenue_ai.revenue_intelligence.contracts import (
    OpportunityRankingResult,
    RankedOpportunity,
    RevenueIntelligenceContext,
    RevenueIntelligenceError,
    RevenueIntelligenceErrorCode,
)
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityScore,
    OpportunityType,
    Recommendation,
    RecommendationPriority,
    RevenueImpact,
    UrgencyLevel,
)


class RuleBasedOpportunityRanker:
    """Ранжирует возможности по подтверждённым данным, не изменяя входные объекты."""

    _URGENCY_SCORES = {
        UrgencyLevel.LOW: 10.0,
        UrgencyLevel.MEDIUM: 40.0,
        UrgencyLevel.HIGH: 70.0,
        UrgencyLevel.CRITICAL: 100.0,
    }
    _CONFIDENCE_SCORES = {
        ConfidenceLevel.LOW: 20.0,
        ConfidenceLevel.MEDIUM: 55.0,
        ConfidenceLevel.HIGH: 85.0,
    }
    _PRIORITY_SCORES = {
        RecommendationPriority.LOW: 25.0,
        RecommendationPriority.MEDIUM: 50.0,
        RecommendationPriority.HIGH: 75.0,
        RecommendationPriority.CRITICAL: 100.0,
    }
    _TYPE_RELEVANCE_SCORES = {
        OpportunityType.REVENUE_GROWTH: 70.0,
        OpportunityType.PRICING: 70.0,
        OpportunityType.RETENTION: 65.0,
        OpportunityType.COST_SAVING: 60.0,
        OpportunityType.SEGMENT: 55.0,
        OpportunityType.OPERATIONAL: 45.0,
    }

    def rank(
        self,
        opportunities: Sequence[BusinessOpportunity],
        *,
        revenue_impacts: Mapping[UUID, RevenueImpact | None] | None = None,
        recommendations: Mapping[UUID, Sequence[Recommendation]] | None = None,
        context: RevenueIntelligenceContext | None = None,
        limit: int = 5,
    ) -> OpportunityRankingResult:
        """Возвращает стабильный TOP-N без изменения переданных объектов."""
        if limit < 1:
            raise ValueError("limit должен быть положительным числом")

        _ = context
        impact_by_opportunity = revenue_impacts or {}
        recommendations_by_opportunity = recommendations or {}
        ranked: list[RankedOpportunity] = []
        errors: list[RevenueIntelligenceError] = []

        for opportunity in opportunities:
            try:
                impact = impact_by_opportunity.get(opportunity.id, opportunity.revenue_impact)
                related_recommendations = list(
                    recommendations_by_opportunity.get(
                        opportunity.id,
                        opportunity.recommended_actions,
                    )
                )
                score = self._calculate_score(
                    opportunity,
                    impact,
                    related_recommendations,
                )
                ranked.append(
                    RankedOpportunity(
                        opportunity=opportunity.model_copy(deep=True),
                        score=score,
                        rank=1,
                        recommendations=[
                            recommendation.model_copy(deep=True)
                            for recommendation in related_recommendations
                        ],
                        revenue_impact=impact.model_copy(deep=True) if impact else None,
                        selection_reason="Ожидает назначения позиции после сортировки.",
                    )
                )
            except Exception:
                errors.append(
                    RevenueIntelligenceError(
                        component=self.__class__.__name__,
                        code=RevenueIntelligenceErrorCode.COMPONENT_FAILURE,
                        message="Не удалось рассчитать оценку одной возможности.",
                        stage="opportunity_ranker",
                        safe_message=(
                            "Одна возможность не ранжирована; "
                            "доступен частичный результат."
                        ),
                        opportunity_id=opportunity.id,
                    )
                )

        ranked.sort(key=self._sort_key)
        selected_count = min(limit, len(ranked))
        selected_ids = {item.opportunity.id for item in ranked[:selected_count]}

        for index, item in enumerate(ranked, start=1):
            item.rank = index
            item.selection_reason = self._selection_reason(
                item,
                selected=item.opportunity.id in selected_ids,
                selection_limit=limit,
            )

        return OpportunityRankingResult(
            ranked_opportunities=ranked,
            selected_opportunities=ranked[:selected_count],
            total_candidates=len(opportunities),
            selection_limit=limit,
            processing_metadata={
                "ranker": self.__class__.__name__,
                "scored_candidates": len(ranked),
                "selection_strategy": "final_score_then_urgency_confidence_deadline_id",
            },
            errors=errors,
        )

    def _calculate_score(
        self,
        opportunity: BusinessOpportunity,
        revenue_impact: RevenueImpact | None,
        recommendations: list[Recommendation],
    ) -> OpportunityScore:
        """Рассчитывает ограниченные частичные оценки на основе доступных фактов."""
        revenue_score, revenue_note = self._revenue_score(revenue_impact)
        urgency_score = self._URGENCY_SCORES[opportunity.urgency]
        confidence_score = self._CONFIDENCE_SCORES[opportunity.confidence]
        relevance_score = self._relevance_score(opportunity)
        deadline_score, deadline_note = self._deadline_score(
            opportunity.created_at,
            recommendations,
        )
        recommendation_score, recommendation_note = self._recommendation_score(
            recommendations
        )

        final_score = round(
            revenue_score * 0.30
            + urgency_score * 0.20
            + confidence_score * 0.15
            + relevance_score * 0.10
            + deadline_score * 0.10
            + recommendation_score * 0.15,
            2,
        )

        explanation_parts = [
            f"Выручка: {revenue_score:.0f}/100 ({revenue_note}).",
            f"Срочность: {urgency_score:.0f}/100 ({opportunity.urgency.value}).",
            f"Уверенность: {confidence_score:.0f}/100 ({opportunity.confidence.value}).",
            f"Релевантность: {relevance_score:.0f}/100 (тип и подтверждающие данные).",
            f"Дедлайн: {deadline_score:.0f}/100 ({deadline_note}).",
            f"Рекомендации: {recommendation_score:.0f}/100 ({recommendation_note}).",
        ]
        return OpportunityScore(
            revenue_score=revenue_score,
            urgency_score=urgency_score,
            confidence_score=confidence_score,
            relevance_score=relevance_score,
            deadline_score=deadline_score,
            recommendation_priority_score=recommendation_score,
            final_score=final_score,
            explanation=" ".join(explanation_parts),
        )

    @staticmethod
    def _revenue_score(revenue_impact: RevenueImpact | None) -> tuple[float, str]:
        if revenue_impact is None or revenue_impact.amount_max is None:
            return 0.0, "денежная оценка отсутствует"

        amount = revenue_impact.amount_max
        if amount <= 10_000:
            return 10.0, "подтверждён небольшой диапазон"
        if amount <= 50_000:
            return 30.0, "подтверждён умеренный диапазон"
        if amount <= 100_000:
            return 50.0, "подтверждён значимый диапазон"
        if amount <= 200_000:
            return 70.0, "подтверждён высокий диапазон"
        return 100.0, "подтверждён очень высокий диапазон"

    def _relevance_score(self, opportunity: BusinessOpportunity) -> float:
        score = self._TYPE_RELEVANCE_SCORES[opportunity.opportunity_type]
        evidence_bonus = min(len(opportunity.evidence) * 5.0, 15.0)
        entity_count = sum(len(values) for values in opportunity.detected_entities.values())
        entity_bonus = min(entity_count * 2.5, 15.0)
        return min(score + evidence_bonus + entity_bonus, 100.0)

    @staticmethod
    def _deadline_score(
        created_at: datetime,
        recommendations: list[Recommendation],
    ) -> tuple[float, str]:
        deadlines = [item.deadline for item in recommendations if item.deadline is not None]
        if not deadlines:
            return 25.0, "дедлайн отсутствует"

        earliest_deadline = min(
            RuleBasedOpportunityRanker._normalize_datetime(item)
            for item in deadlines
        )
        normalized_created_at = RuleBasedOpportunityRanker._normalize_datetime(created_at)
        hours = (earliest_deadline - normalized_created_at).total_seconds() / 3600
        if hours <= 24:
            return 100.0, "подтверждён дедлайн до 24 часов"
        if hours <= 72:
            return 75.0, "подтверждён дедлайн до 72 часов"
        if hours <= 168:
            return 50.0, "подтверждён дедлайн до недели"
        return 30.0, "подтверждён долгосрочный дедлайн"

    def _recommendation_score(
        self,
        recommendations: list[Recommendation],
    ) -> tuple[float, str]:
        if not recommendations:
            return 25.0, "рекомендации отсутствуют"

        priority_score = max(self._PRIORITY_SCORES[item.priority] for item in recommendations)
        count_bonus = min((len(recommendations) - 1) * 5.0, 15.0)
        return min(priority_score + count_bonus, 100.0), (
            f"{len(recommendations)} рекомендаций с подтверждённым приоритетом"
        )

    @staticmethod
    def _sort_key(item: RankedOpportunity) -> tuple[float, float, float, datetime, str]:
        deadlines = [
            recommendation.deadline
            for recommendation in item.recommendations
            if recommendation.deadline is not None
        ]
        deadline = (
            min(
                RuleBasedOpportunityRanker._normalize_datetime(item)
                for item in deadlines
            )
            if deadlines
            else datetime.max.replace(tzinfo=timezone.utc)
        )
        return (
            -item.score.final_score,
            -item.score.urgency_score,
            -item.score.confidence_score,
            deadline,
            str(item.opportunity.id),
        )

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        """Приводит naive и timezone-aware даты к единой шкале UTC."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _selection_reason(
        item: RankedOpportunity,
        *,
        selected: bool,
        selection_limit: int,
    ) -> str:
        if selected:
            return (
                f"Выбрана в TOP-{selection_limit}: место {item.rank}, "
                f"итоговая оценка {item.score.final_score:.2f}/100."
            )
        return (
            f"Не вошла в TOP-{selection_limit}: место {item.rank}, "
            f"итоговая оценка {item.score.final_score:.2f}/100."
        )