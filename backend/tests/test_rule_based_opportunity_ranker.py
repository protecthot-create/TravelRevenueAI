"""Проверки публичного контракта детерминированного ранжировщика возможностей."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from travel_revenue_ai.revenue_intelligence import (
    OpportunityRanker,
    OpportunityRankingResult,
    OpportunityScore,
    RankedOpportunity,
    RuleBasedOpportunityRanker,
)
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityType,
    Recommendation,
    RecommendationPriority,
    RevenueImpact,
    UrgencyLevel,
)

BASE_TIME = datetime(2026, 7, 19, 9, 0, 0)


def make_impact(
    amount_min: float | None = 50_000,
    amount_max: float | None = 100_000,
    *,
    currency: str = "RUB",
) -> RevenueImpact:
    """Создаёт допустимую оценку диапазона выручки для тестов."""
    return RevenueImpact(
        amount_min=amount_min,
        amount_max=amount_max,
        currency=currency,
        confidence=ConfidenceLevel.HIGH,
        calculation_method="Тестовый расчёт",
        explanation="Тестовая подтверждённая оценка.",
        assumptions=["Тестовое допущение"],
    )


def make_recommendation(
    *,
    priority: RecommendationPriority = RecommendationPriority.HIGH,
    deadline: datetime | None = None,
    title: str = "Запустить кампанию",
) -> Recommendation:
    """Создаёт рекомендацию с контролируемым приоритетом и дедлайном."""
    return Recommendation(
        title=title,
        description="Выполнить конкретное действие.",
        reason="Тестовое правило подтверждает действие.",
        priority=priority,
        deadline=deadline,
        supporting_evidence=["Подтверждающий факт"],
    )


def make_opportunity(
    *,
    opportunity_id: UUID | None = None,
    title: str = "Раннее бронирование Турции",
    impact: RevenueImpact | None = None,
    urgency: UrgencyLevel = UrgencyLevel.HIGH,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    recommendations: list[Recommendation] | None = None,
    created_at: datetime = BASE_TIME,
    evidence: list[str] | None = None,
    opportunity_type: OpportunityType = OpportunityType.REVENUE_GROWTH,
    detected_entities: dict[str, list[str]] | None = None,
) -> BusinessOpportunity:
    """Создаёт возможность через публичную доменную модель."""
    return BusinessOpportunity(
        id=opportunity_id or uuid4(),
        title=title,
        summary="Подтверждённый тестовый сигнал с возможностью действия.",
        opportunity_type=opportunity_type,
        revenue_impact=impact,
        urgency=urgency,
        confidence=confidence,
        recommended_actions=recommendations or [],
        created_at=created_at,
        evidence=evidence if evidence is not None else ["Подтверждённый факт"],
        detected_entities=(
            detected_entities if detected_entities is not None else {"country": ["Турция"]}
        ),
    )


def rank(
    opportunities: list[BusinessOpportunity],
    *,
    limit: int = 5,
    revenue_impacts: dict[UUID, RevenueImpact | None] | None = None,
    recommendations: dict[UUID, list[Recommendation]] | None = None,
) -> OpportunityRankingResult:
    """Запускает публичный контракт ранжировщика."""
    return RuleBasedOpportunityRanker().rank(
        opportunities,
        limit=limit,
        revenue_impacts=revenue_impacts,
        recommendations=recommendations,
    )


def test_ranker_satisfies_public_opportunity_ranker_protocol() -> None:
    """Реализация поддерживает опубликованный Protocol."""
    assert isinstance(RuleBasedOpportunityRanker(), OpportunityRanker)


def test_empty_list_returns_valid_empty_result() -> None:
    """Пустой вход возвращает валидный пустой результат."""
    result = rank([])

    assert isinstance(result, OpportunityRankingResult)
    assert result.total_candidates == 0
    assert result.selection_limit == 5
    assert result.ranked_opportunities == []
    assert result.selected_opportunities == []
    assert result.errors == []


def test_single_opportunity_returns_ranked_and_selected_copy() -> None:
    """Одна возможность получает первое место и попадает в TOP-N."""
    opportunity = make_opportunity(impact=make_impact())

    result = rank([opportunity])

    assert result.total_candidates == 1
    assert len(result.ranked_opportunities) == 1
    assert len(result.selected_opportunities) == 1
    item = result.ranked_opportunities[0]
    assert isinstance(item, RankedOpportunity)
    assert isinstance(item.score, OpportunityScore)
    assert item.rank == 1
    assert item.opportunity == opportunity
    assert item.opportunity is not opportunity
    assert "TOP-5" in item.selection_reason


def test_multiple_opportunities_are_ranked_and_selection_is_subset() -> None:
    """Несколько возможностей сортируются, а выбор остаётся подмножеством ranking."""
    opportunities = [
        make_opportunity(impact=make_impact(10_000, 20_000), urgency=UrgencyLevel.LOW),
        make_opportunity(impact=make_impact(100_000, 200_000), urgency=UrgencyLevel.CRITICAL),
        make_opportunity(impact=make_impact(50_000, 100_000), urgency=UrgencyLevel.MEDIUM),
    ]

    result = rank(opportunities, limit=2)

    assert result.total_candidates == 3
    assert len(result.ranked_opportunities) == 3
    assert len(result.selected_opportunities) == 2
    assert [item.rank for item in result.ranked_opportunities] == [1, 2, 3]
    assert result.selected_opportunities == result.ranked_opportunities[:2]


@pytest.mark.parametrize("limit", [3, 5, 10, 2, 1])
def test_top_n_respects_positive_limit(limit: int) -> None:
    """TOP-N возвращает не больше переданного положительного лимита."""
    opportunities = [make_opportunity() for _ in range(6)]

    result = rank(opportunities, limit=limit)

    assert result.selection_limit == limit
    assert len(result.selected_opportunities) == min(limit, len(opportunities))


def test_limit_larger_than_candidates_selects_all() -> None:
    """Лимит больше числа кандидатов выбирает всех доступных кандидатов."""
    opportunities = [make_opportunity(), make_opportunity()]

    result = rank(opportunities, limit=10)

    assert len(result.selected_opportunities) == 2


@pytest.mark.parametrize("limit", [0, -1, -10])
def test_limit_less_than_one_raises_value_error(limit: int) -> None:
    """Неположительный TOP-N запрещён публичным контрактом."""
    with pytest.raises(ValueError, match="положительным"):
        rank([make_opportunity()], limit=limit)


def test_score_components_are_bounded_explained_and_deterministic() -> None:
    """Все частичные оценки и итог лежат в диапазоне 0..100 и повторяемы."""
    opportunity = make_opportunity(
        impact=make_impact(120_000, 250_000),
        urgency=UrgencyLevel.CRITICAL,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(
                priority=RecommendationPriority.CRITICAL,
                deadline=BASE_TIME + timedelta(hours=8),
            )
        ],
        evidence=["Факт 1", "Факт 2", "Факт 3", "Факт 4"],
    )

    first = rank([opportunity]).ranked_opportunities[0].score
    second = rank([opportunity]).ranked_opportunities[0].score

    assert first == second
    for value in (
        first.revenue_score,
        first.urgency_score,
        first.confidence_score,
        first.relevance_score,
        first.deadline_score,
        first.recommendation_priority_score,
        first.final_score,
    ):
        assert 0 <= value <= 100
    assert first.revenue_score == 100
    assert first.urgency_score == 100
    assert first.confidence_score == 85
    assert first.relevance_score > 0
    assert first.deadline_score == 100
    assert first.recommendation_priority_score == 100
    assert first.explanation


@pytest.mark.parametrize(
    ("impact", "expected_score"),
    [
        (make_impact(50_000, 100_000), 50),
        (None, 0),
        (make_impact(None, None), 0),
        (make_impact(50_000, 100_000, currency="USD"), 50),
    ],
)
def test_financial_data_is_safe_and_never_invented(
    impact: RevenueImpact | None,
    expected_score: float,
) -> None:
    """Известные, пустые и неизвестные валютные диапазоны обрабатываются безопасно."""
    opportunity = make_opportunity(impact=impact)

    result = rank([opportunity])
    item = result.ranked_opportunities[0]

    assert item.score.revenue_score == expected_score
    assert item.revenue_impact == impact
    if impact is None:
        assert item.revenue_impact is None
    else:
        assert item.revenue_impact is not impact
        assert item.revenue_impact.amount_min == impact.amount_min
        assert item.revenue_impact.amount_max == impact.amount_max
    assert result.errors == []


def test_high_urgency_confidence_and_earlier_deadline_raise_priority() -> None:
    """Сильные публичные признаки повышают итоговую оценку."""
    common_impact = make_impact()
    low = make_opportunity(
        impact=common_impact,
        urgency=UrgencyLevel.LOW,
        confidence=ConfidenceLevel.LOW,
        recommendations=[
            make_recommendation(
                priority=RecommendationPriority.LOW,
                deadline=BASE_TIME + timedelta(days=14),
            )
        ],
    )
    high = make_opportunity(
        impact=common_impact,
        urgency=UrgencyLevel.CRITICAL,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(
                priority=RecommendationPriority.HIGH,
                deadline=BASE_TIME + timedelta(hours=12),
            )
        ],
    )

    result = rank([low, high])
    scores = {item.opportunity.id: item.score for item in result.ranked_opportunities}

    assert scores[high.id].final_score > scores[low.id].final_score
    assert scores[high.id].urgency_score > scores[low.id].urgency_score
    assert scores[high.id].confidence_score > scores[low.id].confidence_score
    assert scores[high.id].deadline_score > scores[low.id].deadline_score


def test_missing_deadline_and_expired_deadline_are_predictable() -> None:
    """Отсутствующий и просроченный дедлайны не приводят к исключению."""
    without_deadline = make_opportunity(recommendations=[])
    expired = make_opportunity(
        recommendations=[
            make_recommendation(deadline=BASE_TIME - timedelta(hours=1))
        ]
    )

    result = rank([without_deadline, expired])
    scores = {item.opportunity.id: item.score for item in result.ranked_opportunities}

    assert result.errors == []
    assert scores[without_deadline.id].deadline_score == 25
    assert scores[expired.id].deadline_score == 100


def test_timezone_aware_and_naive_datetime_are_supported() -> None:
    """Даты с timezone и без неё приводятся к единой временной шкале."""
    naive = make_opportunity(
        recommendations=[
            make_recommendation(deadline=BASE_TIME + timedelta(hours=12))
        ]
    )
    aware = make_opportunity(
        created_at=BASE_TIME.replace(tzinfo=timezone.utc),
        recommendations=[
            make_recommendation(
                deadline=(BASE_TIME + timedelta(hours=12)).replace(tzinfo=timezone.utc)
            )
        ],
    )

    result = rank([naive, aware])

    assert len(result.ranked_opportunities) == 2
    assert result.errors == []
    assert all(item.score.deadline_score == 100 for item in result.ranked_opportunities)


def test_recommendations_are_copied_for_single_multiple_and_absent_cases() -> None:
    """Одна, несколько и отсутствующие рекомендации не изменяются ranker-ом."""
    single = make_recommendation(priority=RecommendationPriority.HIGH)
    multiple = [
        make_recommendation(priority=RecommendationPriority.MEDIUM),
        make_recommendation(priority=RecommendationPriority.CRITICAL),
    ]
    one = make_opportunity(recommendations=[single])
    many = make_opportunity(recommendations=multiple)
    absent = make_opportunity(recommendations=[])

    result = rank([one, many, absent])
    items = {item.opportunity.id: item for item in result.ranked_opportunities}

    assert len(items[one.id].recommendations) == 1
    assert len(items[many.id].recommendations) == 2
    assert items[many.id].score.recommendation_priority_score == 100
    assert items[absent.id].recommendations == []
    assert items[one.id].recommendations[0] is not single
    assert items[many.id].recommendations[0] is not multiple[0]
    assert one.recommended_actions == [single]
    assert many.recommended_actions == multiple


def test_tie_break_uses_urgency_confidence_deadline_and_stable_uuid() -> None:
    """При равном final_score применяются публично документированные tie-break правила."""
    deadline = BASE_TIME + timedelta(days=14)
    low_urgency = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000020"),
        impact=None,
        urgency=UrgencyLevel.LOW,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(priority=RecommendationPriority.CRITICAL, deadline=deadline)
        ],
    )
    high_urgency = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000010"),
        impact=None,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.LOW,
        recommendations=[
            make_recommendation(priority=RecommendationPriority.HIGH, deadline=deadline)
        ],
        evidence=["Факт 1", "Факт 2", "Факт 3"],
        detected_entities={"country": ["Турция", "Египет", "ОАЭ"]},
    )
    # У обоих кандидатов одинаковый final_score при разных urgency_score.
    assert (
        rank([low_urgency]).ranked_opportunities[0].score.final_score
        == rank([high_urgency]).ranked_opportunities[0].score.final_score
    )
    urgency_result = rank([low_urgency, high_urgency])
    assert urgency_result.ranked_opportunities[0].opportunity.id == high_urgency.id

    low_confidence = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000030"),
        impact=None,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.LOW,
        recommendations=[
            make_recommendation(priority=RecommendationPriority.CRITICAL, deadline=deadline)
        ],
        opportunity_type=OpportunityType.OPERATIONAL,
        evidence=[],
        detected_entities={},
    )
    high_confidence = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000040"),
        impact=None,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(priority=RecommendationPriority.LOW, deadline=deadline)
        ],
        opportunity_type=OpportunityType.COST_SAVING,
        evidence=[],
        detected_entities={},
    )
    assert (
        rank([low_confidence]).ranked_opportunities[0].score.final_score
        == rank([high_confidence]).ranked_opportunities[0].score.final_score
    )
    confidence_result = rank([low_confidence, high_confidence])
    assert confidence_result.ranked_opportunities[0].opportunity.id == high_confidence.id

    later = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000050"),
        impact=None,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(
                priority=RecommendationPriority.LOW,
                deadline=BASE_TIME + timedelta(days=14),
            )
        ],
    )
    earlier = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000060"),
        impact=None,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(
                priority=RecommendationPriority.LOW,
                deadline=BASE_TIME + timedelta(days=10),
            )
        ],
    )
    deadline_result = rank([later, earlier])
    assert deadline_result.ranked_opportunities[0].opportunity.id == earlier.id

    smaller_id = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000001"),
        impact=None,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(priority=RecommendationPriority.LOW, deadline=deadline)
        ],
    )
    larger_id = make_opportunity(
        opportunity_id=UUID("00000000-0000-0000-0000-000000000002"),
        impact=None,
        urgency=UrgencyLevel.HIGH,
        confidence=ConfidenceLevel.HIGH,
        recommendations=[
            make_recommendation(priority=RecommendationPriority.LOW, deadline=deadline)
        ],
    )
    first_run = rank([larger_id, smaller_id])
    second_run = rank([larger_id, smaller_id])
    expected_order = [smaller_id.id, larger_id.id]
    assert [item.opportunity.id for item in first_run.ranked_opportunities] == expected_order
    assert [item.opportunity.id for item in second_run.ranked_opportunities] == expected_order


def test_failed_candidate_is_isolated_and_error_does_not_disclose_payload() -> None:
    """Сбой отдельного кандидата не блокирует остальных и не раскрывает его данные."""
    good = make_opportunity(impact=make_impact())
    bad = BusinessOpportunity.model_construct(
        id=uuid4(),
        title="Секретное название",
        summary="Секретный raw_data и полный сигнал не должны попасть в ошибку.",
        opportunity_type=OpportunityType.REVENUE_GROWTH,
        urgency="not-a-valid-urgency",
        confidence=ConfidenceLevel.HIGH,
        created_at=BASE_TIME,
        recommended_actions=[],
        revenue_impact=None,
        evidence=[],
        detected_entities={},
        source_signal_ids=[],
        score=None,
    )

    result = rank([bad, good])

    assert [item.opportunity.id for item in result.ranked_opportunities] == [good.id]
    assert len(result.errors) == 1
    assert result.errors[0].component == "RuleBasedOpportunityRanker"
    assert "Секретное название" not in result.errors[0].message
    assert "raw_data" not in result.errors[0].message
    assert "полный сигнал" not in result.errors[0].message


def test_input_opportunity_impact_and_recommendation_are_not_mutated() -> None:
    """Ранжирование не меняет объекты входного доменного контракта."""
    impact = make_impact()
    recommendation = make_recommendation(deadline=BASE_TIME + timedelta(hours=12))
    opportunity = make_opportunity(
        impact=impact,
        recommendations=[recommendation],
        evidence=["Исходный факт"],
    )
    original_opportunity = opportunity.model_copy(deep=True)
    original_impact = impact.model_copy(deep=True)
    original_recommendation = recommendation.model_copy(deep=True)

    result = rank([opportunity])
    item = result.ranked_opportunities[0]

    assert opportunity == original_opportunity
    assert impact == original_impact
    assert recommendation == original_recommendation
    assert item.opportunity is not opportunity
    assert item.revenue_impact is not impact
    assert item.recommendations[0] is not recommendation


def test_ranker_module_does_not_import_pipeline_or_infrastructure_layers() -> None:
    """Модуль ranker не зависит от Pipeline, FastAPI, SQLAlchemy или database layer."""
    module_path = (
        Path(__file__).parents[1]
        / "src"
        / "travel_revenue_ai"
        / "revenue_intelligence"
        / "opportunity_ranker.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {"fastapi", "sqlalchemy", "database", "pipeline"} & imported_modules == set()