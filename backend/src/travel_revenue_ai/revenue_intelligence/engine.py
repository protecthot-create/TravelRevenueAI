"""Изолированный оркестратор Revenue Intelligence."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from travel_revenue_ai.revenue_intelligence.contracts import (
    RevenueIntelligenceError,
    RevenueIntelligenceErrorCode,
    RevenueIntelligenceInput,
    RevenueIntelligenceResult,
)
from travel_revenue_ai.revenue_intelligence.interfaces import (
    ConfidenceEstimator,
    OpportunityDetector,
    OpportunityGrouper,
    OpportunityRanker,
    RecommendationBuilder,
    RevenueEstimator,
    UrgencyEstimator,
)
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    Recommendation,
    RevenueImpact,
)


class RevenueIntelligenceEngine:
    """Оркестрирует внедрённые компоненты без инфраструктурных зависимостей."""

    def __init__(
        self,
        *,
        detectors: Iterable[OpportunityDetector] = (),
        revenue_estimator: RevenueEstimator | None = None,
        urgency_estimator: UrgencyEstimator | None = None,
        confidence_estimator: ConfidenceEstimator | None = None,
        recommendation_builder: RecommendationBuilder | None = None,
        opportunity_grouper: OpportunityGrouper | None = None,
        opportunity_ranker: OpportunityRanker | None = None,
    ) -> None:
        self._detectors = tuple(detectors)
        self._revenue_estimator = revenue_estimator
        self._urgency_estimator = urgency_estimator
        self._confidence_estimator = confidence_estimator
        self._recommendation_builder = recommendation_builder
        self._opportunity_grouper = opportunity_grouper
        self._opportunity_ranker = opportunity_ranker

    def process(self, input_data: RevenueIntelligenceInput) -> RevenueIntelligenceResult:
        """Строит детерминированный частичный результат при сбоях компонентов."""
        result = RevenueIntelligenceResult(
            processing_metadata={
                "detectors_configured": len(self._detectors),
                "selection_limit": input_data.selection_limit,
            }
        )
        opportunities = self._detect_opportunities(input_data, result)

        for opportunity in opportunities:
            self._build_recommendations(opportunity, input_data, result)
            self._estimate_revenue(opportunity, input_data, result)
            self._enrich_legacy_attributes(opportunity, input_data, result)

        result.opportunities = opportunities
        result.detected_opportunities = opportunities
        self._group_opportunities(opportunities, input_data, result)
        self._rank_opportunities(opportunities, input_data, result)
        self._populate_metadata(result, input_data)
        return result

    def _detect_opportunities(
        self,
        input_data: RevenueIntelligenceInput,
        result: RevenueIntelligenceResult,
    ) -> list[BusinessOpportunity]:
        """Вызывает детекторы и создаёт независимые копии их результатов."""
        opportunities: list[BusinessOpportunity] = []

        for detector in self._detectors:
            try:
                opportunities.extend(
                    opportunity.model_copy(deep=True)
                    for opportunity in detector.detect(input_data)
                )
            except Exception as error:
                self._record_error(result, "opportunity_detector", detector, error)

        return opportunities

    def _build_recommendations(
        self,
        opportunity: BusinessOpportunity,
        input_data: RevenueIntelligenceInput,
        result: RevenueIntelligenceResult,
    ) -> None:
        """Создаёт рекомендации и сохраняет связь с возможностью."""
        if self._recommendation_builder is None:
            return

        try:
            recommendations = self._recommendation_builder.build(
                opportunity, input_data.context
            )
            opportunity.recommended_actions = recommendations
            result.recommendations.extend(recommendations)
        except Exception as error:
            self._record_error(
                result,
                "recommendation_builder",
                self._recommendation_builder,
                error,
                opportunity.id,
            )

    def _estimate_revenue(
        self,
        opportunity: BusinessOpportunity,
        input_data: RevenueIntelligenceInput,
        result: RevenueIntelligenceResult,
    ) -> None:
        """Создаёт оценку влияния и сохраняет связь с возможностью."""
        if self._revenue_estimator is None:
            return

        try:
            revenue_impact = self._revenue_estimator.estimate(
                opportunity, input_data.context
            )
            opportunity.revenue_impact = revenue_impact
            if revenue_impact is not None:
                result.revenue_impacts.append(revenue_impact)
        except Exception as error:
            self._record_error(
                result,
                "revenue_estimator",
                self._revenue_estimator,
                error,
                opportunity.id,
            )

    def _enrich_legacy_attributes(
        self,
        opportunity: BusinessOpportunity,
        input_data: RevenueIntelligenceInput,
        result: RevenueIntelligenceResult,
    ) -> None:
        """Сохраняет обратную совместимость с прежними необязательными оценками."""
        components = (
            ("urgency_estimator", self._urgency_estimator, "urgency"),
            ("confidence_estimator", self._confidence_estimator, "confidence"),
        )
        for stage, component, attribute in components:
            if component is None:
                continue
            try:
                setattr(
                    opportunity,
                    attribute,
                    component.estimate(opportunity, input_data.context),
                )
            except Exception as error:
                self._record_error(result, stage, component, error, opportunity.id)

    def _group_opportunities(
        self,
        opportunities: list[BusinessOpportunity],
        input_data: RevenueIntelligenceInput,
        result: RevenueIntelligenceResult,
    ) -> None:
        """Группирует возможности, если компонент внедрён."""
        if self._opportunity_grouper is None:
            return

        try:
            result.groups = self._opportunity_grouper.group(
                opportunities, input_data.context
            )
        except Exception as error:
            self._record_error(
                result,
                "opportunity_grouper",
                self._opportunity_grouper,
                error,
            )

    def _rank_opportunities(
        self,
        opportunities: list[BusinessOpportunity],
        input_data: RevenueIntelligenceInput,
        result: RevenueIntelligenceResult,
    ) -> None:
        """Ранжирует связанные данные, не прерывая частичный результат."""
        if self._opportunity_ranker is None:
            return

        revenue_impacts: dict[UUID, RevenueImpact | None] = {
            opportunity.id: opportunity.revenue_impact for opportunity in opportunities
        }
        recommendations: dict[UUID, list[Recommendation]] = {
            opportunity.id: opportunity.recommended_actions
            for opportunity in opportunities
        }
        try:
            ranking_result = self._opportunity_ranker.rank(
                opportunities,
                revenue_impacts=revenue_impacts,
                recommendations=recommendations,
                context=input_data.context,
                limit=input_data.selection_limit,
            )
            result.ranking_result = ranking_result
            result.selected_opportunities = ranking_result.selected_opportunities
            result.errors.extend(ranking_result.errors)
        except Exception as error:
            self._record_error(
                result,
                "opportunity_ranker",
                self._opportunity_ranker,
                error,
            )

    @staticmethod
    def _populate_metadata(
        result: RevenueIntelligenceResult,
        input_data: RevenueIntelligenceInput,
    ) -> None:
        """Заполняет только детерминированные счётчики обработки."""
        ranking_result = result.ranking_result
        result.processing_metadata.update(
            {
                "opportunities_detected": len(result.detected_opportunities),
                "recommendations_built": len(result.recommendations),
                "revenue_impacts_created": len(result.revenue_impacts),
                "candidates_ranked": ranking_result.total_candidates
                if ranking_result is not None
                else 0,
                "opportunities_selected": len(result.selected_opportunities),
                "errors_count": len(result.errors),
                "selection_limit": input_data.selection_limit,
            }
        )

    @staticmethod
    def _record_error(
        result: RevenueIntelligenceResult,
        stage: str,
        component: object,
        error: Exception,
        opportunity_id: UUID | None = None,
    ) -> None:
        """Сохраняет безопасную ошибку без исходных данных и трассировки."""
        result.errors.append(
            RevenueIntelligenceError(
                component=type(component).__name__,
                code=RevenueIntelligenceErrorCode.COMPONENT_FAILURE,
                message=(
                    "Компонент завершился с ошибкой: "
                    f"{type(error).__name__}"
                ),
                stage=stage,
                safe_message="Этап не завершён; доступен частичный результат.",
                opportunity_id=opportunity_id,
            )
        )