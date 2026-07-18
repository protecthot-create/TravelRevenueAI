"""Unit-тесты изолированного Intelligence Layer."""

from __future__ import annotations

from datetime import date

from travel_revenue_ai.intelligence import (
    DuplicateSignalDetector,
    EntityExtractor,
    SignalEnrichmentService,
    SignalPriority,
    SignalPriorityEstimator,
)


def test_entity_extractor_finds_travel_entities_and_deadline() -> None:
    """Извлекаются словарные сущности, скидка, валюта и срок акции."""
    result = EntityExtractor().extract(
        "Coral Travel: скидка 25% на Турцию, Анталья. "
        "Отель Hotel Sunrise. Вылет Turkish Airlines. Акция до 2026-07-20, цена 900 €.",
        reference_date=date(2026, 7, 18),
    )

    assert result.countries == ["Турция"]
    assert result.cities == ["Анталья"]
    assert result.operators == ["Coral Travel"]
    assert result.airlines == ["Turkish Airlines"]
    assert result.hotels == ["Sunrise"]
    assert result.discounts == [25]
    assert result.currencies == ["EUR"]
    assert result.deadline == "2026-07-20"
    assert result.language == "ru"


def test_duplicate_detector_detects_same_email_message_id() -> None:
    """Одинаковый Message-ID email распознаётся как transport-дубликат."""
    raw_data = {
        "channel": "email",
        "message_id": "<offer-1@example.test>",
        "normalized_text": "Скидка 20% на Турцию",
    }
    result = DuplicateSignalDetector().detect(
        raw_data,
        [{"channel": "email", "message_id": "<offer-1@example.test>", "normalized_text": "другое"}],
    )

    assert result.is_duplicate is True
    assert result.reasons == ["email_message_id"]
    assert result.matched_identifiers == ["email:<offer-1@example.test>"]


def test_duplicate_detector_detects_cross_source_text_repeat() -> None:
    """Одинаковый текст email и Telegram даёт межканальный hash-дубликат."""
    result = DuplicateSignalDetector().detect(
        {"channel": "telegram", "chat_id": "77", "message_id": "10", "text": "  СКИДКА 20%  "},
        [{"channel": "email", "message_id": "<offer-2@example.test>", "normalized_text": "скидка 20%"}],
    )

    assert result.is_duplicate is True
    assert result.reasons == ["normalized_text_hash"]
    assert result.normalized_text_hash is not None


def test_priority_estimator_uses_urgency_discount_and_operator() -> None:
    """Комбинация срочности, большой скидки и оператора становится HIGH."""
    result = SignalPriorityEstimator().estimate(
        text="Срочно: акция заканчивается сегодня",
        discounts=[25],
        deadline="2026-07-18",
        operators=["Anex Tour"],
        reference_date=date(2026, 7, 18),
    )

    assert result is SignalPriority.HIGH


def test_priority_estimator_returns_low_without_signals() -> None:
    """Без скидок, сроков и ключевых слов приоритет остаётся LOW."""
    result = SignalPriorityEstimator().estimate(
        text="Информационное сообщение",
        discounts=[],
        deadline=None,
        operators=[],
        reference_date=date(2026, 7, 18),
    )

    assert result is SignalPriority.LOW


def test_enrichment_adds_intelligence_metadata_without_mutating_raw_data() -> None:
    """Enrichment создаёт копию и сохраняет ранее существующую metadata."""
    raw_data = {
        "channel": "telegram",
        "chat_id": "77",
        "message_id": "11",
        "text": "Срочно! Anex Tour: скидка 30% на Египет до 20 июля.",
        "metadata": {"source_note": "keep"},
    }

    enriched = SignalEnrichmentService().enrich(
        raw_data,
        known_signals=[
            {
                "channel": "email",
                "message_id": "<offer-3@example.test>",
                "normalized_text": "срочно! anex tour: скидка 30% на египет до 20 июля.",
            }
        ],
        reference_date=date(2026, 7, 18),
    )

    assert "intelligence" not in raw_data["metadata"]
    assert enriched["metadata"]["source_note"] == "keep"
    intelligence = enriched["metadata"]["intelligence"]
    assert intelligence["countries"] == ["Египет"]
    assert intelligence["discounts"] == [30]
    assert intelligence["deadline"] == "2026-07-20"
    assert intelligence["priority"] == "HIGH"
    assert intelligence["duplicates"]["is_duplicate"] is True