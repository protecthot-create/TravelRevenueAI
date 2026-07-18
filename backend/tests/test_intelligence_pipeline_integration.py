"""Интеграционные тесты Intelligence Layer в полном pipeline."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from uuid import UUID

import pytest

from travel_revenue_ai.models.signal import Signal, SignalStatusEnum, SignalTypeEnum
from travel_revenue_ai.services.decision_card_service import DecisionCardService
from travel_revenue_ai.services.filtering_service import FilteringService
from travel_revenue_ai.services.morning_brief_service import MorningBriefService
from travel_revenue_ai.services.pipeline_service import PipelineService
from travel_revenue_ai.services.revenue_scoring_service import RevenueScoringService


AGENCY_ID = UUID("11111111-1111-1111-1111-111111111111")
SOURCE_ID = UUID("22222222-2222-2222-2222-222222222222")


def make_signal(channel: str) -> Signal:
    """Создаёт нормализованный сигнал email или Telegram для полного конвейера."""
    if channel == "email":
        channel_data = {
            "channel": "email",
            "message_id": "<turkey-offer@example.test>",
            "subject": "Coral Travel: скидка 25% на Турцию",
            "body": "Срочно! Акция действует до 20 июля.",
        }
    else:
        channel_data = {
            "channel": "telegram",
            "chat_id": "travel-offers",
            "message_id": "501",
            "text": "Coral Travel: скидка 25% на Турцию. Срочно, акция до 20 июля.",
        }

    return Signal(
        agency_id=AGENCY_ID,
        source_id=SOURCE_ID,
        signal_type=SignalTypeEnum.opportunity,
        status=SignalStatusEnum.normalized,
        raw_data={
            **channel_data,
            "title": "Раннее бронирование Турция",
            "money_effect": 85_000,
            "deadline_hours": 48,
            "probability": 0.72,
            "controllability": 1.0,
            "risk": False,
            "repeatable": True,
            "context_match": True,
            "season": "peak",
            "summary": "Спрос растёт, окно действия короткое",
            "source_name": channel,
            "metadata": {"source_marker": channel},
        },
    )


def run_baseline_pipeline(signal: Signal) -> tuple[object, object]:
    """Выполняет прежний маршрут без Intelligence Layer для регрессии output."""
    scoring_service = RevenueScoringService()
    filtering_service = FilteringService()
    decision_card_service = DecisionCardService()
    morning_brief_service = MorningBriefService(default_date=date(2026, 7, 18))

    score_results = scoring_service.score_signals([signal])
    filtering_result = filtering_service.filter_signals(score_results)
    cards = decision_card_service.generate_cards(
        [
            (filter_result, score_results[0], signal.raw_data)
            for filter_result in filtering_result.passed_signals
        ]
    )
    return score_results[0], morning_brief_service.generate_brief(cards)


@pytest.mark.parametrize("channel", ["email", "telegram"])
def test_source_signal_is_enriched_before_scoring_without_changing_score(
    channel: str,
) -> None:
    """Email и Telegram проходят enrichment до scoring, сохраняя результат scoring."""
    baseline_signal = make_signal(channel)
    baseline_score, _ = run_baseline_pipeline(baseline_signal)

    signal = make_signal(channel)
    original_raw_data = deepcopy(signal.raw_data)
    original_type = signal.signal_type
    original_status = signal.status

    pipeline = PipelineService(
        morning_brief_service=MorningBriefService(default_date=date(2026, 7, 18))
    )
    pipeline._enrich_signals([signal])
    enriched_score = RevenueScoringService().score_signal(signal)

    assert signal.signal_type == original_type
    assert signal.status == original_status
    assert signal.raw_data["metadata"]["source_marker"] == channel
    assert signal.raw_data["metadata"]["intelligence"]["priority"] in {
        "LOW",
        "MEDIUM",
        "HIGH",
    }
    assert {
        key: value
        for key, value in signal.raw_data.items()
        if key != "metadata"
    } == {
        key: value
        for key, value in original_raw_data.items()
        if key != "metadata"
    }
    assert signal.raw_data["metadata"]["source_marker"] == original_raw_data["metadata"][
        "source_marker"
    ]
    assert enriched_score == baseline_score


@pytest.mark.parametrize("channel", ["email", "telegram"])
def test_full_pipeline_keeps_decision_cards_and_morning_brief_unchanged(
    channel: str,
) -> None:
    """Intelligence metadata не меняет Decision Cards и Morning Brief."""
    baseline_signal = make_signal(channel)
    baseline_score, baseline_brief = run_baseline_pipeline(baseline_signal)

    signal = make_signal(channel)
    pipeline = PipelineService(
        morning_brief_service=MorningBriefService(default_date=date(2026, 7, 18))
    )
    enriched_brief = pipeline.generate_morning_brief([signal])
    enriched_score = RevenueScoringService().score_signal(signal)

    assert signal.raw_data["metadata"]["intelligence"]
    assert enriched_score == baseline_score
    assert enriched_brief.summary is not None
    assert baseline_brief.summary is not None
    assert enriched_brief.summary.full_text == baseline_brief.summary.full_text
    assert enriched_brief.opportunities_count == baseline_brief.opportunities_count
    assert enriched_brief.risks_count == baseline_brief.risks_count
    assert enriched_brief.market_insights_count == baseline_brief.market_insights_count

    assert [
        (card.title, card.score, card.what_to_do, card.money_effect_display)
        for card in enriched_brief.opportunities
    ] == [
        (card.title, card.score, card.what_to_do, card.money_effect_display)
        for card in baseline_brief.opportunities
    ]