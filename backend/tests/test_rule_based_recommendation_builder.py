"""Тесты детерминированного построителя рекомендаций."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceContext
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityType,
    Recommendation,
    RecommendationActionType,
    RecommendationPriority,
    UrgencyLevel,
)
from travel_revenue_ai.revenue_intelligence.recommendation_builder import (
    RuleBasedRecommendationBuilder,
)


@pytest.fixture
def builder() -> RuleBasedRecommendationBuilder:
    """Возвращает тестируемый изолированный Builder."""
    return RuleBasedRecommendationBuilder()


def make_opportunity(
    opportunity_type: OpportunityType,
    *,
    urgency: UrgencyLevel = UrgencyLevel.HIGH,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    entities: dict[str, list[str]] | None = None,
    evidence: list[str] | None = None,
) -> BusinessOpportunity:
    """Создаёт подтверждённую возможность с фиксированным временем."""
    return BusinessOpportunity(
        title="Тестовая возможность",
        summary="Тестовое описание подтверждённой возможности.",
        opportunity_type=opportunity_type,
        source_signal_ids=[uuid4()],
        detected_entities=entities or {},
        urgency=urgency,
        confidence=confidence,
        evidence=evidence if evidence is not None else ["Подтверждённый источник."],
        created_at=datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
    )


def action_types(recommendations: list[Recommendation]) -> set[RecommendationActionType]:
    """Возвращает множество типов действий результата."""
    return {recommendation.action_type for recommendation in recommendations}


def test_revenue_growth_creates_entity_confirmed_promotion_actions(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Рост выручки создаёт только действия, подтверждённые сущностями каналов."""
    opportunity = make_opportunity(
        OpportunityType.REVENUE_GROWTH,
        entities={
            "client_segment": ["семьи"],
            "messenger": ["telegram"],
            "social_media": ["vk"],
            "website": ["landing"],
        },
    )

    recommendations = builder.build(opportunity, RevenueIntelligenceContext())

    assert action_types(recommendations) == {
        RecommendationActionType.CALL_CLIENTS,
        RecommendationActionType.SEND_EMAIL_CAMPAIGN,
        RecommendationActionType.SEND_MESSENGER_CAMPAIGN,
        RecommendationActionType.PUBLISH_SOCIAL_MEDIA_POST,
        RecommendationActionType.UPDATE_WEBSITE_BANNER,
    }


def test_retention_creates_multiple_recommendations(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Удержание создаёт несколько отдельных действий."""
    recommendations = builder.build(
        make_opportunity(OpportunityType.RETENTION),
        RevenueIntelligenceContext(),
    )

    assert action_types(recommendations) == {
        RecommendationActionType.CALL_CLIENTS,
        RecommendationActionType.SEND_MESSENGER_CAMPAIGN,
        RecommendationActionType.CREATE_CRM_TASK,
    }


def test_pricing_with_tour_operator_creates_manager_and_operator_actions(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Ценовая возможность с туроператором создаёт контактное действие."""
    recommendations = builder.build(
        make_opportunity(
            OpportunityType.PRICING,
            entities={"tour_operator": ["Тестовый оператор"]},
        ),
        RevenueIntelligenceContext(),
    )

    assert action_types(recommendations) == {
        RecommendationActionType.NOTIFY_SALES_MANAGER,
        RecommendationActionType.CREATE_CRM_TASK,
        RecommendationActionType.CONTACT_TOUR_OPERATOR,
    }


@pytest.mark.parametrize(
    "opportunity_type",
    [OpportunityType.COST_SAVING, OpportunityType.OPERATIONAL],
)
def test_operational_types_notify_manager_and_create_task(
    builder: RuleBasedRecommendationBuilder,
    opportunity_type: OpportunityType,
) -> None:
    """Операционные типы не создают маркетинговые действия."""
    recommendations = builder.build(
        make_opportunity(opportunity_type),
        RevenueIntelligenceContext(),
    )

    assert action_types(recommendations) == {
        RecommendationActionType.NOTIFY_SALES_MANAGER,
        RecommendationActionType.CREATE_CRM_TASK,
    }


def test_low_confidence_low_urgency_is_ignored(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Слабый и несрочный сигнал не создаёт активных рекомендаций."""
    recommendations = builder.build(
        make_opportunity(
            OpportunityType.REVENUE_GROWTH,
            urgency=UrgencyLevel.LOW,
            confidence=ConfidenceLevel.LOW,
            entities={"client_segment": ["семьи"]},
        ),
        RevenueIntelligenceContext(),
    )

    assert action_types(recommendations) == {RecommendationActionType.IGNORE}


def test_low_confidence_urgent_signal_waits_for_confirmation(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Срочный, но слабый сигнал не запускает необоснованных действий."""
    recommendations = builder.build(
        make_opportunity(
            OpportunityType.PRICING,
            urgency=UrgencyLevel.HIGH,
            confidence=ConfidenceLevel.LOW,
        ),
        RevenueIntelligenceContext(),
    )

    assert action_types(recommendations) == {RecommendationActionType.WAIT}
    assert recommendations[0].deadline == datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)


def test_critical_opportunity_is_escalated_with_critical_deadline(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Критическая возможность всегда получает действие эскалации."""
    recommendations = builder.build(
        make_opportunity(
            OpportunityType.OPERATIONAL,
            urgency=UrgencyLevel.CRITICAL,
        ),
        RevenueIntelligenceContext(),
    )

    escalation = next(
        item
        for item in recommendations
        if item.action_type == RecommendationActionType.ESCALATE_URGENT_OPPORTUNITY
    )
    assert escalation.priority == RecommendationPriority.CRITICAL
    assert escalation.deadline == datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def test_medium_high_confidence_has_high_priority_and_monitoring(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Средняя срочность с высокой уверенностью повышает приоритет и создаёт мониторинг."""
    recommendations = builder.build(
        make_opportunity(
            OpportunityType.OPERATIONAL,
            urgency=UrgencyLevel.MEDIUM,
            confidence=ConfidenceLevel.HIGH,
        ),
        RevenueIntelligenceContext(),
    )

    active = next(
        item
        for item in recommendations
        if item.action_type == RecommendationActionType.NOTIFY_SALES_MANAGER
    )
    monitor = next(
        item
        for item in recommendations
        if item.action_type == RecommendationActionType.MONITOR_PROMOTION
    )
    assert active.priority == RecommendationPriority.HIGH
    assert active.deadline == datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
    assert monitor.priority == RecommendationPriority.LOW


def test_builder_returns_empty_list_without_evidence(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Без доказательств Builder не создаёт даже пассивных рекомендаций."""
    recommendations = builder.build(
        make_opportunity(OpportunityType.REVENUE_GROWTH, evidence=[]),
        RevenueIntelligenceContext(),
    )

    assert recommendations == []


def test_each_recommendation_has_full_explainable_contract(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Каждая рекомендация содержит требуемые объяснимые поля."""
    opportunity = make_opportunity(
        OpportunityType.PRICING,
        entities={"tour_operator": ["Тестовый оператор"]},
        evidence=["Тариф поставщика изменён."],
    )

    recommendations = builder.build(opportunity, RevenueIntelligenceContext())

    assert recommendations
    for recommendation in recommendations:
        assert recommendation.action_type
        assert recommendation.title
        assert recommendation.description
        assert recommendation.reason
        assert recommendation.priority
        assert recommendation.deadline is not None
        assert recommendation.expected_result
        assert recommendation.required_entities == {"tour_operator": ["Тестовый оператор"]}
        assert recommendation.supporting_evidence == ["Тариф поставщика изменён."]
        assert recommendation.supporting_signal_ids == opportunity.source_signal_ids


def test_duplicate_recommendations_are_merged_without_losing_evidence(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Одинаковые рекомендации объединяются с сохранением сущностей и доказательств."""
    first = Recommendation(
        action_type=RecommendationActionType.MONITOR_PROMOTION,
        title="Наблюдать",
        description="Первое описание.",
        reason="Первое правило.",
        priority=RecommendationPriority.LOW,
        required_entities={"country": ["Турция"]},
        supporting_evidence=["Доказательство 1"],
        supporting_signal_ids=[uuid4()],
    )
    second = Recommendation(
        action_type=RecommendationActionType.MONITOR_PROMOTION,
        title="Наблюдать",
        description="Второе описание.",
        reason="Второе правило.",
        priority=RecommendationPriority.LOW,
        required_entities={"country": ["Египет"]},
        supporting_evidence=["Доказательство 2", "Доказательство 1"],
        supporting_signal_ids=[first.supporting_signal_ids[0], uuid4()],
    )

    merged = builder._merge_duplicates([first, second])

    assert len(merged) == 1
    assert merged[0].required_entities == {"country": ["Турция", "Египет"]}
    assert merged[0].supporting_evidence == ["Доказательство 1", "Доказательство 2"]
    assert len(merged[0].supporting_signal_ids) == 2


def test_no_false_promotion_actions_without_channel_entities(
    builder: RuleBasedRecommendationBuilder,
) -> None:
    """Рост выручки без сущностей каналов не выдумывает маркетинговые действия."""
    recommendations = builder.build(
        make_opportunity(OpportunityType.REVENUE_GROWTH),
        RevenueIntelligenceContext(),
    )

    assert recommendations == []