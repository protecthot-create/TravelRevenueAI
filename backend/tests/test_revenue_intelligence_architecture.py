"""Архитектурные тесты изолированного слоя Revenue Intelligence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from travel_revenue_ai.revenue_intelligence.confidence_estimator import (
    NullConfidenceEstimator,
)
from travel_revenue_ai.revenue_intelligence.contracts import (
    RevenueIntelligenceContext,
    RevenueIntelligenceErrorCode,
    RevenueIntelligenceInput,
    RevenueIntelligenceResult,
)
from travel_revenue_ai.revenue_intelligence.engine import RevenueIntelligenceEngine
from travel_revenue_ai.revenue_intelligence.interfaces import (
    ConfidenceEstimator,
    OpportunityDetector,
    OpportunityGrouper,
    RecommendationBuilder,
    RevenueEstimator,
    UrgencyEstimator,
)
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityGroup,
    OpportunityScore,
    OpportunityType,
    Recommendation,
    RecommendationPriority,
    RevenueImpact,
    RevenueOpportunity,
    RevenueRisk,
    RiskType,
    UrgencyLevel,
)
from travel_revenue_ai.revenue_intelligence.opportunity_detector import (
    NullOpportunityDetector,
)
from travel_revenue_ai.revenue_intelligence.opportunity_grouping import (
    NullOpportunityGrouper,
)
from travel_revenue_ai.revenue_intelligence.recommendation_builder import (
    NullRecommendationBuilder,
)
from travel_revenue_ai.revenue_intelligence.revenue_estimator import (
    NullRevenueEstimator,
)
from travel_revenue_ai.revenue_intelligence.urgency_estimator import (
    NullUrgencyEstimator,
)


def make_input() -> RevenueIntelligenceInput:
    """Создаёт независимый входной контракт для тестов."""
    return RevenueIntelligenceInput(
        signal_id=uuid4(),
        signal_type="opportunity",
        raw_data={"nested": {"value": "original"}},
        context=RevenueIntelligenceContext(agency_context={"segment": "small"}),
    )


def make_opportunity() -> BusinessOpportunity:
    """Создаёт минимальную доменную возможность."""
    return BusinessOpportunity(
        title="Тестовая возможность",
        summary="Проверка архитектурного контракта.",
        opportunity_type=OpportunityType.REVENUE_GROWTH,
    )


def test_all_domain_models_are_created_and_serialized() -> None:
    """Все доменные модели создаются и сериализуются Pydantic."""
    impact = RevenueImpact(
        amount_min=10_000,
        amount_max=20_000,
        currency="RUB",
        calculation_method="test",
        assumptions=["Данные тестовые"],
    )
    revenue_opportunity = RevenueOpportunity(
        estimated_revenue=15_000,
        revenue_range_min=10_000,
        revenue_range_max=20_000,
        affected_clients_count=5,
        conversion_probability=0.5,
    )
    risk = RevenueRisk(
        estimated_loss=30_000,
        risk_type=RiskType.MARGIN_LOSS,
        probability=0.7,
    )
    recommendation = Recommendation(
        action="Проверить расчёт",
        rationale="Проверка контракта",
        priority=RecommendationPriority.HIGH,
    )
    score = OpportunityScore(
        revenue_score=10,
        urgency_score=5,
        confidence_score=8,
        relevance_score=7,
        final_score=30,
        explanation="Тестовая оценка",
    )
    opportunity = make_opportunity().model_copy(
        update={
            "revenue_impact": impact,
            "recommended_actions": [recommendation],
            "score": score,
        }
    )
    group = OpportunityGroup(
        title="Тестовая группа",
        opportunities=[opportunity],
        combined_revenue_impact=impact,
    )

    payload = group.model_dump(mode="json")

    assert revenue_opportunity.estimated_revenue == 15_000
    assert risk.estimated_loss == 30_000
    assert payload["opportunities"][0]["title"] == "Тестовая возможность"
    assert payload["combined_revenue_impact"]["amount_max"] == 20_000


def test_enums_are_string_values() -> None:
    """Enum сохраняют стабильные строковые значения контрактов."""
    assert OpportunityType.PRICING == "pricing"
    assert RiskType.CANCELLATION == "cancellation"
    assert UrgencyLevel.CRITICAL == "critical"
    assert ConfidenceLevel.HIGH == "high"
    assert RecommendationPriority.MEDIUM == "medium"
    assert RevenueIntelligenceErrorCode.COMPONENT_FAILURE == "component_failure"


def test_input_from_signal_makes_deep_copy_and_preserves_signal() -> None:
    """from_signal создаёт снимок без изменения Signal и его mutable-полей."""
    agency_id = uuid4()
    signal = SimpleNamespace(
        signal_id=uuid4(),
        signal_type="opportunity",
        agency_id=agency_id,
        raw_data={
            "nested": {"value": "original"},
            "metadata": {"intelligence": {"source": "test"}},
        },
        score=42,
        status="normalized",
        created_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    original_raw_data = deepcopy(signal.raw_data)
    original_score = signal.score
    original_status = signal.status

    input_data = RevenueIntelligenceInput.from_signal(signal)
    input_data.raw_data["nested"]["value"] = "changed"
    input_data.context.intelligence_metadata["source"] = "changed"

    assert input_data.context.agency_id == agency_id
    assert signal.raw_data == original_raw_data
    assert signal.score == original_score
    assert signal.status == original_status
    assert input_data.raw_data["nested"]["value"] == "changed"
    assert signal.raw_data["nested"]["value"] == "original"
    assert signal.raw_data["metadata"]["intelligence"]["source"] == "test"


def test_empty_result_is_valid_and_serializable() -> None:
    """Пустой результат Engine является валидным контрактом."""
    result = RevenueIntelligenceResult()

    assert result.model_dump() == {
        "opportunities": [],
        "detected_opportunities": [],
        "risks": [],
        "recommendations": [],
        "revenue_impacts": [],
        "groups": [],
        "ranking_result": None,
        "selected_opportunities": [],
        "processing_metadata": {},
        "errors": [],
    }


def test_null_components_match_protocols_and_do_not_change_inputs() -> None:
    """Null-компоненты возвращают нейтральные значения без побочных эффектов."""
    input_data = make_input()
    opportunity = make_opportunity()
    input_snapshot = input_data.model_copy(deep=True)
    opportunity_snapshot = opportunity.model_copy(deep=True)
    context = input_data.context

    detector = NullOpportunityDetector()
    revenue_estimator = NullRevenueEstimator()
    urgency_estimator = NullUrgencyEstimator()
    confidence_estimator = NullConfidenceEstimator()
    recommendation_builder = NullRecommendationBuilder()
    grouper = NullOpportunityGrouper()

    assert isinstance(detector, OpportunityDetector)
    assert isinstance(revenue_estimator, RevenueEstimator)
    assert isinstance(urgency_estimator, UrgencyEstimator)
    assert isinstance(confidence_estimator, ConfidenceEstimator)
    assert isinstance(recommendation_builder, RecommendationBuilder)
    assert isinstance(grouper, OpportunityGrouper)
    assert detector.detect(input_data) == []
    assert revenue_estimator.estimate(opportunity, context) is None
    assert urgency_estimator.estimate(opportunity, context) == UrgencyLevel.LOW
    assert confidence_estimator.estimate(opportunity, context) == ConfidenceLevel.LOW
    assert recommendation_builder.build(opportunity, context) == []
    assert grouper.group([opportunity], context) == []
    assert input_data == input_snapshot
    assert opportunity == opportunity_snapshot


def test_engine_without_components_returns_empty_valid_result() -> None:
    """Engine без компонентов возвращает валидный пустой результат."""
    result = RevenueIntelligenceEngine().process(make_input())

    assert result.opportunities == []
    assert result.recommendations == []
    assert result.groups == []
    assert result.errors == []
    assert result.detected_opportunities == []
    assert result.revenue_impacts == []
    assert result.ranking_result is None
    assert result.selected_opportunities == []
    assert result.processing_metadata == {
        "detectors_configured": 0,
        "selection_limit": 5,
        "opportunities_detected": 0,
        "recommendations_built": 0,
        "revenue_impacts_created": 0,
        "candidates_ranked": 0,
        "opportunities_selected": 0,
        "errors_count": 0,
    }


def test_engine_uses_injected_components_and_preserves_input() -> None:
    """Engine вызывает внедрённые компоненты и не изменяет входной контракт."""

    class Detector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            return [make_opportunity()]

    class Revenue:
        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> RevenueImpact:
            return RevenueImpact(
                amount_min=10_000,
                amount_max=12_000,
                currency="RUB",
                calculation_method="test",
            )

    class Urgency:
        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> UrgencyLevel:
            return UrgencyLevel.HIGH

    class Confidence:
        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> ConfidenceLevel:
            return ConfidenceLevel.HIGH

    class Builder:
        def build(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> list[Recommendation]:
            return [
                Recommendation(
                    action="Выполнить действие",
                    rationale="Тест DI",
                    priority=RecommendationPriority.HIGH,
                )
            ]

    class Grouper:
        def group(
            self,
            opportunities: list[BusinessOpportunity],
            context: RevenueIntelligenceContext,
        ) -> list[OpportunityGroup]:
            return [OpportunityGroup(title="Группа", opportunities=opportunities)]

    input_data = make_input()
    raw_data_before = deepcopy(input_data.raw_data)
    result = RevenueIntelligenceEngine(
        detectors=[Detector()],
        revenue_estimator=Revenue(),
        urgency_estimator=Urgency(),
        confidence_estimator=Confidence(),
        recommendation_builder=Builder(),
        opportunity_grouper=Grouper(),
    ).process(input_data)

    opportunity = result.opportunities[0]
    assert opportunity.revenue_impact is not None
    assert opportunity.urgency == UrgencyLevel.HIGH
    assert opportunity.confidence == ConfidenceLevel.HIGH
    assert len(result.recommendations) == 1
    assert len(result.groups) == 1
    assert input_data.raw_data == raw_data_before


def test_engine_records_component_error_and_continues() -> None:
    """Ошибка одного компонента сохраняется, а следующие компоненты выполняются."""

    class FailingDetector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            raise RuntimeError("boom")

    class WorkingDetector:
        def detect(self, input_data: RevenueIntelligenceInput) -> list[BusinessOpportunity]:
            return [make_opportunity()]

    class FailingEstimator:
        def estimate(
            self,
            opportunity: BusinessOpportunity,
            context: RevenueIntelligenceContext,
        ) -> RevenueImpact:
            raise ValueError("bad estimate")

    result = RevenueIntelligenceEngine(
        detectors=[FailingDetector(), WorkingDetector()],
        revenue_estimator=FailingEstimator(),
    ).process(make_input())

    assert len(result.opportunities) == 1
    assert len(result.errors) == 2
    assert {error.component for error in result.errors} == {
        "FailingDetector",
        "FailingEstimator",
    }
    assert all(
        error.code == RevenueIntelligenceErrorCode.COMPONENT_FAILURE
        for error in result.errors
    )


def test_engine_does_not_import_pipeline_or_infrastructure() -> None:
    """Изолированный Engine не зависит от Pipeline, FastAPI или БД."""
    import inspect

    import travel_revenue_ai.revenue_intelligence.engine as engine_module

    source = inspect.getsource(engine_module).lower()

    assert "pipeline" not in source
    assert "fastapi" not in source
    assert "sqlalchemy" not in source
    assert "database" not in source