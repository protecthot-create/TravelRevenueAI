"""Unit-тесты детерминированного детектора возможностей."""

from __future__ import annotations

from uuid import uuid4

import pytest

from travel_revenue_ai.revenue_intelligence.contracts import RevenueIntelligenceInput
from travel_revenue_ai.revenue_intelligence.models import ConfidenceLevel, UrgencyLevel
from travel_revenue_ai.revenue_intelligence.opportunity_detector import (
    RuleBasedOpportunityDetector,
)


@pytest.fixture
def detector() -> RuleBasedOpportunityDetector:
    """Создаёт независимый rule-based детектор."""
    return RuleBasedOpportunityDetector()


def make_input(text: str) -> RevenueIntelligenceInput:
    """Создаёт минимальный входной контракт с текстом сигнала."""
    return RevenueIntelligenceInput(
        signal_id=uuid4(),
        signal_type="opportunity",
        raw_data={"subject": text},
    )


@pytest.mark.parametrize(
    ("text", "expected_type"),
    [
        ("Акция на туры в Турцию до 2026-08-01", "Promotion"),
        ("Акция: скидка 20% на отели в Турции", "Discount"),
        ("Акция: повышенная комиссия 5% от туроператора", "Commission Increase"),
        ("Акция: ограниченное предложение на отдых", "Limited Offer"),
        ("Акция: горящий тур в Египет", "Last Minute"),
        ("Акция: раннее бронирование Турции", "Early Booking"),
        ("Акция: снижение цены на туры в ОАЭ", "Price Drop"),
        ("Акция: новый чартер в Турцию", "New Charter"),
        ("Акция: новое направление — Оман", "New Destination"),
        ("Акция: бонусная программа для агентств", "Bonus Program"),
        ("Акция отеля Hilton в Турции", "Hotel Promotion"),
        ("Акция на авиабилеты Аэрофлота", "Flight Promotion"),
    ],
)
def test_detects_each_supported_opportunity_type(
    detector: RuleBasedOpportunityDetector,
    text: str,
    expected_type: str,
) -> None:
    """Каждый заявленный тип определяется отдельным KB-правилом."""
    opportunities = detector.detect(make_input(text))

    opportunity = next(item for item in opportunities if item.title == expected_type)

    assert opportunity.evidence
    assert opportunity.summary.startswith(f"Обнаружена возможность типа {expected_type}")
    assert opportunity.source_signal_ids
    assert opportunity.confidence in {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}


def test_preserves_evidence_entities_confidence_and_urgency(
    detector: RuleBasedOpportunityDetector,
) -> None:
    """Результат включает все обязательные для объяснения поля."""
    opportunities = detector.detect(
        make_input("Акция: скидка 25% на отели Hilton в Турции сегодня до 2026-08-01")
    )

    discount = next(item for item in opportunities if item.title == "Discount")

    assert "скидка" in discount.evidence
    assert "25%" in discount.evidence
    assert "сегодня" in discount.evidence
    assert discount.detected_entities["countries"] == ["Турция"]
    assert discount.detected_entities["hotels"] == ["Hilton"]
    assert discount.detected_entities["discounts"] == ["25"]
    assert discount.detected_entities["deadline"] == ["2026-08-01"]
    assert discount.confidence == ConfidenceLevel.HIGH
    assert discount.urgency == UrgencyLevel.CRITICAL


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Общий обзор туристического рынка за неделю.",
        "Снижение цены на туры в Турцию без рекламного предложения.",
        "Акционер компании сообщил о финансовом результате.",
        "У нас сегодня обычное рабочее совещание.",
    ],
)
def test_returns_empty_for_non_promotional_or_empty_text(
    detector: RuleBasedOpportunityDetector,
    text: str,
) -> None:
    """Шум и текст без пары promo-маркер + правило не создают возможностей."""
    assert detector.detect(make_input(text)) == []


def test_detects_multiple_opportunities_from_one_signal(
    detector: RuleBasedOpportunityDetector,
) -> None:
    """Один сигнал может подтвердить несколько независимых типов."""
    opportunities = detector.detect(
        make_input(
            "Акция: раннее бронирование и скидка 15% на новый чартер "
            "в Турцию сегодня"
        )
    )

    titles = {opportunity.title for opportunity in opportunities}

    assert {"Promotion", "Discount", "Early Booking", "New Charter"} <= titles
    assert len(opportunities) == 4