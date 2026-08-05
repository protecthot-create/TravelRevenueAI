"""Проверки детерминированного оценщика влияния на выручку."""

from __future__ import annotations

import pytest

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceContext
from travel_revenue_ai.revenue_intelligence.models import (
    BusinessOpportunity,
    ConfidenceLevel,
    OpportunityType,
    UrgencyLevel,
)
from travel_revenue_ai.revenue_intelligence.revenue_estimator import (
    NullRevenueEstimator,
    RuleBasedRevenueEstimator,
)


@pytest.fixture
def context() -> RevenueIntelligenceContext:
    """Создаёт изолированный контекст без данных агентства."""
    return RevenueIntelligenceContext()


@pytest.fixture
def estimator() -> RuleBasedRevenueEstimator:
    """Создаёт тестируемый rule-based estimator."""
    return RuleBasedRevenueEstimator()


def make_opportunity(
    *,
    opportunity_type: OpportunityType = OpportunityType.REVENUE_GROWTH,
    evidence: list[str] | None = None,
    confidence: ConfidenceLevel = ConfidenceLevel.LOW,
    urgency: UrgencyLevel = UrgencyLevel.LOW,
    detected_entities: dict[str, list[str]] | None = None,
) -> BusinessOpportunity:
    """Создаёт минимальную возможность для сценариев оценщика."""
    return BusinessOpportunity(
        title="Тестовая возможность",
        summary="Проверка детерминированной оценки.",
        opportunity_type=opportunity_type,
        evidence=evidence or [],
        confidence=confidence,
        urgency=urgency,
        detected_entities=detected_entities or {},
    )


@pytest.mark.parametrize("opportunity_type", list(OpportunityType))
def test_estimates_explicit_range_for_every_supported_opportunity_type(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
    opportunity_type: OpportunityType,
) -> None:
    """Все поддерживаемые типы получают одинаково прозрачную оценку."""
    impact = estimator.estimate(
        make_opportunity(
            opportunity_type=opportunity_type,
            evidence=["Подтверждённый потенциал: от 10 000 до 25 000 ₽."],
        ),
        context,
    )

    assert impact.amount_min == 10_000
    assert impact.amount_max == 25_000
    assert impact.currency == "RUB"
    assert impact.calculation_method == "rule_based_explicit_evidence_range"


@pytest.mark.parametrize(
    ("evidence", "amount_min", "amount_max", "currency"),
    [
        (["Потенциал: от 10 000 до 25 000 ₽."], 10_000, 25_000, "RUB"),
        (["Потенциал: 1\u00a0500–2\u00a0750 RUB."], 1_500, 2_750, "RUB"),
        (["Потенциал: 1250.5-2500.75 usd."], 1250.5, 2500.75, "USD"),
        (["Потенциал: 15,5 до 20,75 €."], 15.5, 20.75, "EUR"),
        (["Потенциал: 5 000—7 000 рублей."], 5_000, 7_000, "RUB"),
    ],
)
def test_parses_supported_explicit_money_ranges(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
    evidence: list[str],
    amount_min: float,
    amount_max: float,
    currency: str,
) -> None:
    """Оценщик распознаёт поддерживаемые разделители, числа и валюты."""
    impact = estimator.estimate(make_opportunity(evidence=evidence), context)

    assert impact.amount_min == amount_min
    assert impact.amount_max == amount_max
    assert impact.currency == currency


@pytest.mark.parametrize(
    "evidence",
    [
        [],
        ["Есть высокий спрос, но денежный эффект не указан."],
        ["Потенциал: 20 000 ₽."],
        ["Потенциал: от 20 000 до 40 000."],
        ["Потенциал: от 20 000 RUB до 40 000 USD."],
    ],
)
def test_returns_unknown_without_complete_explicit_range(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
    evidence: list[str],
) -> None:
    """Неполные денежные данные не превращаются в фиктивный прогноз."""
    impact = estimator.estimate(make_opportunity(evidence=evidence), context)

    assert impact.amount_min is None
    assert impact.amount_max is None
    assert impact.confidence == ConfidenceLevel.LOW
    assert impact.calculation_method == "unknown_insufficient_explicit_evidence"
    assert "не выводятся из косвенных признаков" in impact.explanation


def test_returns_unknown_for_reversed_explicit_range(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
) -> None:
    """Обратные границы не исправляются автоматически и не дают сумму."""
    impact = estimator.estimate(
        make_opportunity(evidence=["Потенциал: от 30 000 до 10 000 ₽."]),
        context,
    )

    assert impact.amount_min is None
    assert impact.amount_max is None
    assert impact.calculation_method == "rule_based_explicit_evidence_range"
    assert impact.assumptions == [
        "Диапазон не исправляется автоматически.",
        "Нужен источник с границами в возрастающем порядке.",
    ]


@pytest.mark.parametrize(
    ("confidence", "urgency", "detected_entities", "expected_confidence"),
    [
        (
            ConfidenceLevel.HIGH,
            UrgencyLevel.CRITICAL,
            {"destination": ["Турция"]},
            ConfidenceLevel.HIGH,
        ),
        (
            ConfidenceLevel.HIGH,
            UrgencyLevel.HIGH,
            {},
            ConfidenceLevel.MEDIUM,
        ),
        (
            ConfidenceLevel.HIGH,
            UrgencyLevel.MEDIUM,
            {"destination": ["Турция"]},
            ConfidenceLevel.MEDIUM,
        ),
        (
            ConfidenceLevel.MEDIUM,
            UrgencyLevel.CRITICAL,
            {"destination": ["Турция"]},
            ConfidenceLevel.MEDIUM,
        ),
        (
            ConfidenceLevel.LOW,
            UrgencyLevel.CRITICAL,
            {"destination": ["Турция"]},
            ConfidenceLevel.LOW,
        ),
    ],
)
def test_confidence_uses_only_documented_qualitative_signals(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
    confidence: ConfidenceLevel,
    urgency: UrgencyLevel,
    detected_entities: dict[str, list[str]],
    expected_confidence: ConfidenceLevel,
) -> None:
    """Confidence не повышается за счёт денежного диапазона или типа возможности."""
    impact = estimator.estimate(
        make_opportunity(
            evidence=["Потенциал: от 10 000 до 20 000 ₽."],
            confidence=confidence,
            urgency=urgency,
            detected_entities=detected_entities,
        ),
        context,
    )

    assert impact.confidence == expected_confidence


def test_includes_calculation_method_and_explicit_assumptions(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
) -> None:
    """Оценка фиксирует метод и допущения, необходимые для аудита результата."""
    opportunity = make_opportunity(
        opportunity_type=OpportunityType.PRICING,
        evidence=["Потенциал: от 10 000 до 20 000 ₽."],
        confidence=ConfidenceLevel.MEDIUM,
        urgency=UrgencyLevel.HIGH,
    )

    impact = estimator.estimate(opportunity, context)

    assert impact.calculation_method == "rule_based_explicit_evidence_range"
    assert impact.assumptions == [
        "Денежный диапазон в evidence относится к данной возможности.",
        "Валюта распознана по маркеру в той же строке evidence.",
        "Тип возможности использован только для контекста: pricing.",
        "Срочность использована только для confidence: high.",
        "Исходный confidence возможности: medium.",
    ]


def test_does_not_invent_amount_from_opportunity_attributes(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
) -> None:
    """Высокая срочность и confidence без диапазона не создают денежную оценку."""
    opportunity = make_opportunity(
        opportunity_type=OpportunityType.RETENTION,
        evidence=["Клиенты повторно интересуются направлением."],
        confidence=ConfidenceLevel.HIGH,
        urgency=UrgencyLevel.CRITICAL,
        detected_entities={"destination": ["ОАЭ"]},
    )

    impact = estimator.estimate(opportunity, context)

    assert impact.amount_min is None
    assert impact.amount_max is None
    assert impact.calculation_method == "unknown_insufficient_explicit_evidence"


def test_unknown_opportunity_type_does_not_affect_range_extraction(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
) -> None:
    """Неизвестный тип не участвует в расчёте и не мешает явному диапазону."""
    opportunity = BusinessOpportunity.model_construct(
        title="Неизвестный тип",
        summary="Проверка изоляции расчёта от классификации.",
        opportunity_type="future_type",
        evidence=["Потенциал: от 12 000 до 18 000 ₽."],
        confidence=ConfidenceLevel.LOW,
        urgency=UrgencyLevel.LOW,
        detected_entities={},
    )

    impact = estimator.estimate(opportunity, context)

    assert impact.amount_min == 12_000
    assert impact.amount_max == 18_000
    assert impact.currency == "RUB"
    assert "future_type" in impact.assumptions[2]


def test_uses_first_valid_range_in_evidence_order(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
) -> None:
    """Несколько доказательств не смешиваются: выбирается первый валидный диапазон."""
    impact = estimator.estimate(
        make_opportunity(
            evidence=[
                "Первый подтверждённый диапазон: от 10 000 до 15 000 ₽.",
                "Позднее уточнение: от 30 000 до 45 000 ₽.",
            ]
        ),
        context,
    )

    assert impact.amount_min == 10_000
    assert impact.amount_max == 15_000


def test_estimation_is_deterministic_and_does_not_mutate_inputs(
    estimator: RuleBasedRevenueEstimator,
    context: RevenueIntelligenceContext,
) -> None:
    """Одинаковые входы возвращают одинаковый результат без изменения объектов."""
    opportunity = make_opportunity(
        evidence=["Потенциал: от 10 000 до 20 000 ₽."],
        confidence=ConfidenceLevel.HIGH,
        urgency=UrgencyLevel.HIGH,
        detected_entities={"destination": ["Турция"]},
    )
    initial_opportunity = opportunity.model_dump(mode="json")
    initial_context = context.model_dump(mode="json")

    first_impact = estimator.estimate(opportunity, context)
    second_impact = estimator.estimate(opportunity, context)

    assert first_impact.model_dump(mode="json") == second_impact.model_dump(mode="json")
    assert opportunity.model_dump(mode="json") == initial_opportunity
    assert context.model_dump(mode="json") == initial_context


def test_null_estimator_never_creates_estimate(
    context: RevenueIntelligenceContext,
) -> None:
    """Null estimator сохраняет безопасное поведение по умолчанию."""
    impact = NullRevenueEstimator().estimate(
        make_opportunity(evidence=["Потенциал: от 10 000 до 20 000 ₽."]),
        context,
    )

    assert impact is None