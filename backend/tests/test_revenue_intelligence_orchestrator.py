"""Smoke-проверки изолированного Revenue Intelligence Orchestrator."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import ModuleType
from uuid import UUID

import pytest
from pydantic import ValidationError

from travel_revenue_ai.revenue_intelligence.contracts import (
    OpportunityRankingResult,
    RankedOpportunity,
    RevenueIntelligenceContext,
    RevenueIntelligenceInput,
    RevenueIntelligenceResult,
)
from travel_revenue_ai.revenue_intelligence.engine import RevenueIntelligenceEngine
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
from travel_revenue_ai.revenue_intelligence.opportunity_ranker import (
    RuleBasedOpportunityRanker,
)

FIRST_OPPORTUNITY_ID = UUID("00000000-0000-0000-0000-000000000001")
SECOND_OPPORTUNITY_ID = UUID("00000000-0000-0000-0000-000000000002")
CREATED_AT = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def make_input(*, selection_limit: int = 5) -> RevenueIntelligenceInput:
    """Создаёт фиксированный вход без инфраструктурных зависимостей."""
    return RevenueIntelligenceInput(
        signal_id=UUID("00000000-0000-0000-0000-000000000010"),
        signal_type="opportunity",
        context=RevenueIntelligenceContext(agency_context={"segment": "small"}),
        selection_limit=selection_limit,
    )


class StaticDetector:
    """Возвращает фиксированные возможности для smoke-проверки."""

    def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
        _ = input_data
        return [
            BusinessOpportunity(
                id=FIRST_OPPORTUNITY_ID,
                title="Раннее бронирование",
                summary="Подтверждён спрос на направление.",
                opportunity_type=OpportunityType.REVENUE_GROWTH,
                urgency=UrgencyLevel.HIGH,
                confidence=ConfidenceLevel.HIGH,
                created_at=CREATED_AT,
            ),
            BusinessOpportunity(
                id=SECOND_OPPORTUNITY_ID,
                title="Пакетная продажа",
                summary="Можно повысить средний чек.",
                opportunity_type=OpportunityType.PRICING,
                urgency=UrgencyLevel.MEDIUM,
                confidence=ConfidenceLevel.MEDIUM,
                created_at=CREATED_AT,
            ),
        ]


class StaticRecommendationBuilder:
    """Строит детерминированную рекомендацию для каждой возможности."""

    def build(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> list[Recommendation]:
        _ = context
        return [
            Recommendation(
                title=f"Действие: {opportunity.title}",
                description="Выполнить проверяемое действие.",
                reason="Smoke-проверка.",
                priority=RecommendationPriority.HIGH,
                deadline=CREATED_AT + timedelta(hours=24),
            )
        ]


class StaticRevenueEstimator:
    """Создаёт фиксированную оценку без внешних данных."""

    def estimate(
        self,
        opportunity: BusinessOpportunity,
        context: RevenueIntelligenceContext,
    ) -> RevenueImpact | None:
        _ = context
        amount_max = 100_000 if opportunity.id == FIRST_OPPORTUNITY_ID else 50_000
        return RevenueImpact(
            amount_min=amount_max - 20_000,
            amount_max=amount_max,
            currency="RUB",
            calculation_method="smoke_test",
        )


class StaticRanker:
    """Выбирает TOP-N для изолированной проверки orchestration-контракта."""

    def rank(
        self,
        opportunities: list[BusinessOpportunity],
        *,
        revenue_impacts: object = None,
        recommendations: object = None,
        context: object = None,
        limit: int = 5,
    ) -> OpportunityRankingResult:
        _ = revenue_impacts, recommendations, context
        ranked = [
            RankedOpportunity(
                opportunity=opportunity,
                score=OpportunityScore(
                    revenue_score=0,
                    urgency_score=0,
                    confidence_score=0,
                    relevance_score=0,
                    final_score=0,
                    explanation="Тестовая оценка.",
                ),
                rank=index,
                selection_reason="Детерминированный выбор тестового ranker.",
            )
            for index, opportunity in enumerate(opportunities, start=1)
        ]
        return OpportunityRankingResult(
            ranked_opportunities=ranked,
            selected_opportunities=ranked[:limit],
            total_candidates=len(opportunities),
            selection_limit=limit,
        )


def make_engine(
    *,
    detectors: list[object] | None = None,
    builder: object | None = None,
    estimator: object | None = None,
    ranker: object | None = None,
) -> RevenueIntelligenceEngine:
    """Создаёт orchestrator с внедрёнными изолированными зависимостями."""
    return RevenueIntelligenceEngine(
        detectors=detectors if detectors is not None else [StaticDetector()],
        recommendation_builder=(
            builder if builder is not None else StaticRecommendationBuilder()
        ),
        revenue_estimator=estimator if estimator is not None else StaticRevenueEstimator(),
        opportunity_ranker=ranker if ranker is not None else StaticRanker(),
    )


def test_orchestrator_runs_full_flow_and_is_deterministic() -> None:
    """Detector → Builder → Estimator → Ranker формируют стабильный TOP-N."""
    input_data = make_input(selection_limit=1)

    first_result = make_engine().process(input_data)
    second_result = make_engine().process(input_data)

    assert len(first_result.detected_opportunities) == 2
    assert len(first_result.recommendations) == 2
    assert len(first_result.revenue_impacts) == 2
    assert first_result.ranking_result is not None
    assert first_result.ranking_result.total_candidates == 2
    assert len(first_result.selected_opportunities) == 1
    assert first_result.selected_opportunities[0].opportunity.id == FIRST_OPPORTUNITY_ID
    assert first_result.processing_metadata == {
        "detectors_configured": 1,
        "selection_limit": 1,
        "opportunities_detected": 2,
        "recommendations_built": 2,
        "revenue_impacts_created": 2,
        "candidates_ranked": 2,
        "opportunities_selected": 1,
        "errors_count": 0,
    }
    assert first_result.model_dump(mode="json") == second_result.model_dump(mode="json")


def test_orchestrator_uses_injected_components() -> None:
    """Оркестратор вызывает экземпляры зависимостей, переданные через DI."""

    class RecordingDetector(StaticDetector):
        def __init__(self) -> None:
            self.calls = 0

        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            self.calls += 1
            return super().detect(input_data)

    class RecordingBuilder(StaticRecommendationBuilder):
        def __init__(self) -> None:
            self.opportunity_ids: list[UUID] = []

        def build(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> list[Recommendation]:
            self.opportunity_ids.append(opportunity.id)
            return super().build(opportunity, context)

    class RecordingEstimator(StaticRevenueEstimator):
        def __init__(self) -> None:
            self.opportunity_ids: list[UUID] = []

        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> RevenueImpact | None:
            self.opportunity_ids.append(opportunity.id)
            return super().estimate(opportunity, context)

    detector = RecordingDetector()
    builder = RecordingBuilder()
    estimator = RecordingEstimator()
    engine = RevenueIntelligenceEngine(
        detectors=[detector],
        recommendation_builder=builder,
        revenue_estimator=estimator,
        opportunity_ranker=StaticRanker(),
    )

    result = engine.process(make_input(selection_limit=2))

    assert detector.calls == 1
    assert builder.opportunity_ids == [FIRST_OPPORTUNITY_ID, SECOND_OPPORTUNITY_ID]
    assert estimator.opportunity_ids == [FIRST_OPPORTUNITY_ID, SECOND_OPPORTUNITY_ID]
    assert len(result.detected_opportunities) == 2


def test_orchestrator_returns_partial_result_for_one_builder_failure() -> None:
    """Ошибка Builder одной возможности не отменяет estimation и ranking остальных."""

    class PartiallyFailingBuilder(StaticRecommendationBuilder):
        def build(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> list[Recommendation]:
            if opportunity.id == SECOND_OPPORTUNITY_ID:
                raise RuntimeError("raw email content must not escape")
            return super().build(opportunity, context)

    result = make_engine(builder=PartiallyFailingBuilder()).process(make_input())

    assert len(result.detected_opportunities) == 2
    assert len(result.recommendations) == 1
    assert len(result.revenue_impacts) == 2
    assert result.ranking_result is not None
    assert len(result.selected_opportunities) == 2
    assert len(result.errors) == 1
    error = result.errors[0]
    assert error.stage == "recommendation_builder"
    assert error.opportunity_id == SECOND_OPPORTUNITY_ID
    assert "raw email content" not in error.message
    assert "raw email content" not in error.safe_message
    assert error.safe_message == "Этап не завершён; доступен частичный результат."


def test_orchestrator_keeps_successful_detector_result_when_another_detector_fails() -> None:
    """Сбой одного detector не отменяет возможности от следующего detector."""

    class FailingDetector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            _ = input_data
            raise RuntimeError("Traceback: raw_data={'signal': 'полный текст сигнала'}")

    result = make_engine(
        detectors=[FailingDetector(), StaticDetector()]
    ).process(make_input())

    assert len(result.detected_opportunities) == 2
    assert len(result.recommendations) == 2
    assert len(result.revenue_impacts) == 2
    assert result.processing_metadata["errors_count"] == 1
    assert result.errors[0].stage == "opportunity_detector"
    assert result.errors[0].safe_message


def test_orchestrator_returns_valid_result_when_all_detectors_fail() -> None:
    """Сбои всех detector возвращают валидный пустой частичный результат."""

    class FailingDetector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            _ = input_data
            raise RuntimeError("detector failure")

    result = make_engine(
        detectors=[FailingDetector(), FailingDetector()]
    ).process(make_input(selection_limit=2))

    assert isinstance(result, RevenueIntelligenceResult)
    assert result.detected_opportunities == []
    assert result.recommendations == []
    assert result.revenue_impacts == []
    assert result.ranking_result is not None
    assert result.ranking_result.total_candidates == 0
    assert len(result.errors) == 2
    assert result.processing_metadata["errors_count"] == 2
    assert all(error.stage == "opportunity_detector" for error in result.errors)
    assert all(error.safe_message for error in result.errors)
    assert all(error.opportunity_id is None for error in result.errors)


def test_orchestrator_returns_partial_result_for_one_estimator_failure() -> None:
    """Ошибка Estimator одной возможности не отменяет результаты остальных."""

    class PartiallyFailingEstimator(StaticRevenueEstimator):
        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> RevenueImpact | None:
            if opportunity.id == SECOND_OPPORTUNITY_ID:
                raise RuntimeError("telegram: секретный текст сообщения")
            return super().estimate(opportunity, context)

    result = make_engine(estimator=PartiallyFailingEstimator()).process(make_input())

    assert len(result.detected_opportunities) == 2
    assert len(result.recommendations) == 2
    assert len(result.revenue_impacts) == 1
    assert result.revenue_impacts[0].amount_max == 100_000
    assert result.ranking_result is not None
    assert len(result.selected_opportunities) == 2
    assert len(result.errors) == 1
    error = result.errors[0]
    assert error.stage == "revenue_estimator"
    assert error.safe_message
    assert error.opportunity_id == SECOND_OPPORTUNITY_ID


def test_orchestrator_keeps_partial_data_when_ranker_fails() -> None:
    """Сбой Ranker не удаляет результаты предыдущих этапов."""

    class FailingRanker:
        def rank(
            self,
            opportunities: list[BusinessOpportunity],
            **kwargs: object,
        ) -> OpportunityRankingResult:
            _ = opportunities, kwargs
            raise RuntimeError("ranking failure")

    result = make_engine(ranker=FailingRanker()).process(make_input())

    assert len(result.detected_opportunities) == 2
    assert len(result.recommendations) == 2
    assert len(result.revenue_impacts) == 2
    assert result.ranking_result is None
    assert result.selected_opportunities == []
    assert len(result.errors) == 1
    error = result.errors[0]
    assert error.stage == "opportunity_ranker"
    assert error.safe_message
    assert error.opportunity_id is None


def test_orchestrator_exposes_only_safe_public_errors() -> None:
    """Публичные ошибки содержат контекст этапа без исходных данных и секретов."""

    class FailingDetector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            _ = input_data
            raise RuntimeError(
                "Traceback (most recent call last): raw_data={'x': 1}; "
                "полный текст сигнала; email: client@example.com; "
                "telegram: secret chat; api_key=super-secret"
            )

    class FailingBuilder(StaticRecommendationBuilder):
        def build(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> list[Recommendation]:
            if opportunity.id == SECOND_OPPORTUNITY_ID:
                raise RuntimeError("raw_data email: client@example.com")
            return super().build(opportunity, context)

    class FailingEstimator(StaticRevenueEstimator):
        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> RevenueImpact | None:
            if opportunity.id == FIRST_OPPORTUNITY_ID:
                raise RuntimeError("telegram: secret chat api_key=super-secret")
            return super().estimate(opportunity, context)

    class FailingRanker:
        def rank(
            self,
            opportunities: list[BusinessOpportunity],
            **kwargs: object,
        ) -> OpportunityRankingResult:
            _ = opportunities, kwargs
            raise RuntimeError("Traceback: полный текст сигнала")

    result = make_engine(
        detectors=[FailingDetector(), StaticDetector()],
        builder=FailingBuilder(),
        estimator=FailingEstimator(),
        ranker=FailingRanker(),
    ).process(make_input())

    assert result.processing_metadata["errors_count"] == len(result.errors) == 4
    assert {error.stage for error in result.errors} == {
        "opportunity_detector",
        "recommendation_builder",
        "revenue_estimator",
        "opportunity_ranker",
    }
    assert {
        error.opportunity_id
        for error in result.errors
        if error.stage in {"recommendation_builder", "revenue_estimator"}
    } == {FIRST_OPPORTUNITY_ID, SECOND_OPPORTUNITY_ID}
    assert all(
        error.opportunity_id is None
        for error in result.errors
        if error.stage in {"opportunity_detector", "opportunity_ranker"}
    )

    serialized_errors = str([error.model_dump() for error in result.errors]).lower()
    for forbidden_value in (
        "traceback",
        "raw_data",
        "полный текст сигнала",
        "client@example.com",
        "telegram:",
        "super-secret",
    ):
        assert forbidden_value not in serialized_errors
    assert all(error.stage and error.safe_message for error in result.errors)


def test_orchestrator_handles_empty_detector_result() -> None:
    """Пустой detector возвращает валидный ранжированный пустой результат."""

    class EmptyDetector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            _ = input_data
            return []

    result = RevenueIntelligenceEngine(
        detectors=[EmptyDetector()],
        opportunity_ranker=RuleBasedOpportunityRanker(),
    ).process(make_input(selection_limit=3))

    assert result.detected_opportunities == []
    assert result.recommendations == []
    assert result.revenue_impacts == []
    assert result.ranking_result is not None
    assert result.ranking_result.total_candidates == 0
    assert result.selected_opportunities == []
    assert result.processing_metadata["selection_limit"] == 3
    assert result.processing_metadata["errors_count"] == 0


def test_selection_limit_must_be_positive() -> None:
    """Входной контракт явно отклоняет selection_limit меньше единицы."""
    with pytest.raises(ValidationError):
        make_input(selection_limit=0)


def test_orchestrator_metadata_matches_actually_processed_partial_data() -> None:
    """Metadata отражает результаты всех этапов, включая частичные сбои."""

    class FailingDetector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            _ = input_data
            raise RuntimeError("detector failure")

    class PartiallyFailingBuilder(StaticRecommendationBuilder):
        def build(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> list[Recommendation]:
            if opportunity.id == SECOND_OPPORTUNITY_ID:
                raise RuntimeError("builder failure")
            return super().build(opportunity, context)

    class PartiallyFailingEstimator(StaticRevenueEstimator):
        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> RevenueImpact | None:
            if opportunity.id == SECOND_OPPORTUNITY_ID:
                raise RuntimeError("estimator failure")
            return super().estimate(opportunity, context)

    result = make_engine(
        detectors=[FailingDetector(), StaticDetector()],
        builder=PartiallyFailingBuilder(),
        estimator=PartiallyFailingEstimator(),
    ).process(make_input(selection_limit=1))

    assert result.processing_metadata == {
        "detectors_configured": 2,
        "selection_limit": 1,
        "opportunities_detected": 2,
        "recommendations_built": 1,
        "revenue_impacts_created": 1,
        "candidates_ranked": 2,
        "opportunities_selected": 1,
        "errors_count": 3,
    }
    assert result.processing_metadata["opportunities_detected"] == len(
        result.detected_opportunities
    )
    assert result.processing_metadata["recommendations_built"] == len(
        result.recommendations
    )
    assert result.processing_metadata["revenue_impacts_created"] == len(
        result.revenue_impacts
    )
    assert result.ranking_result is not None
    assert result.processing_metadata["candidates_ranked"] == result.ranking_result.total_candidates
    assert result.processing_metadata["opportunities_selected"] == len(
        result.selected_opportunities
    )
    assert result.processing_metadata["errors_count"] == len(result.errors)


def test_orchestrator_repeats_full_business_result_with_stable_ranking_and_scores() -> None:
    """Одинаковый вход сохраняет порядок, оценки и сериализованный результат."""
    input_data = make_input(selection_limit=2)

    first_result = make_engine().process(input_data)
    second_result = make_engine().process(input_data)

    assert first_result.ranking_result is not None
    assert second_result.ranking_result is not None
    assert [
        item.opportunity.id for item in first_result.ranking_result.ranked_opportunities
    ] == [
        FIRST_OPPORTUNITY_ID,
        SECOND_OPPORTUNITY_ID,
    ]
    assert [
        item.opportunity.id for item in first_result.selected_opportunities
    ] == [
        item.opportunity.id for item in second_result.selected_opportunities
    ]
    assert [
        item.score.model_dump(mode="json")
        for item in first_result.ranking_result.ranked_opportunities
    ] == [
        item.score.model_dump(mode="json")
        for item in second_result.ranking_result.ranked_opportunities
    ]
    assert first_result.model_dump(mode="json") == second_result.model_dump(mode="json")


def test_orchestrator_does_not_mutate_input_or_component_owned_domain_objects() -> None:
    """Engine работает с копиями и не меняет переданные входные доменные объекты."""
    input_data = RevenueIntelligenceInput(
        signal_id=UUID("00000000-0000-0000-0000-000000000020"),
        signal_type="opportunity",
        raw_data={"source": {"payload": ["initial"]}},
        context=RevenueIntelligenceContext(
            agency_context={"segment": "small", "flags": ["priority"]}
        ),
        selection_limit=1,
    )
    opportunity = BusinessOpportunity(
        id=FIRST_OPPORTUNITY_ID,
        title="Внешняя возможность",
        summary="Исходный объект detector.",
        opportunity_type=OpportunityType.REVENUE_GROWTH,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.HIGH,
        created_at=CREATED_AT,
    )
    recommendation = Recommendation(
        title="Внешняя рекомендация",
        description="Исходный объект builder.",
        reason="Проверка неизменяемости.",
        priority=RecommendationPriority.HIGH,
        deadline=CREATED_AT + timedelta(hours=24),
    )
    revenue_impact = RevenueImpact(
        amount_min=80_000,
        amount_max=100_000,
        currency="RUB",
        calculation_method="immutability_test",
    )

    class ObjectDetector:
        def detect(self, received_input: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            assert received_input is input_data
            return [opportunity]

    class ObjectBuilder:
        def build(
            self,
            received_opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> list[Recommendation]:
            _ = received_opportunity, context
            return [recommendation]

    class ObjectEstimator:
        def estimate(
            self,
            received_opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> RevenueImpact:
            _ = received_opportunity, context
            return revenue_impact

    input_snapshot = input_data.model_dump(mode="json")
    opportunity_snapshot = opportunity.model_dump(mode="json")
    recommendation_snapshot = recommendation.model_dump(mode="json")
    revenue_impact_snapshot = revenue_impact.model_dump(mode="json")

    result = RevenueIntelligenceEngine(
        detectors=[ObjectDetector()],
        recommendation_builder=ObjectBuilder(),
        revenue_estimator=ObjectEstimator(),
        opportunity_ranker=StaticRanker(),
    ).process(input_data)

    assert result.detected_opportunities[0] is not opportunity
    assert input_data.model_dump(mode="json") == input_snapshot
    assert opportunity.model_dump(mode="json") == opportunity_snapshot
    assert recommendation.model_dump(mode="json") == recommendation_snapshot
    assert revenue_impact.model_dump(mode="json") == revenue_impact_snapshot


def test_orchestrator_public_imports_do_not_cross_architectural_boundaries() -> None:
    """Публичные импорты Engine не связывают его с HTTP, БД и delivery-слоями."""
    engine_module = importlib.import_module(
        "travel_revenue_ai.revenue_intelligence.engine"
    )
    imported_module_names = {
        value.__name__
        for name, value in vars(engine_module).items()
        if not name.startswith("_") and isinstance(value, ModuleType)
    }

    forbidden_module_parts = (
        "pipeline_service",
        "fastapi",
        "sqlalchemy",
        "database",
        "decision_card",
        "morning_brief",
    )

    assert all(
        forbidden_part not in module_name.lower()
        for module_name in imported_module_names
        for forbidden_part in forbidden_module_parts
    )
    assert "PipelineService" not in vars(engine_module)
    assert "FastAPI" not in vars(engine_module)
